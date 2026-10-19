"""Conservative eligibility checks for superseded Windows desktop runtimes."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

EXECUTABLES = ('codex.exe', 'codex-code-mode-host.exe', 'codex-windows-sandbox-setup.exe',
               'codex-command-runner.exe', 'node.exe', 'node_repl.exe', 'rg.exe')
HASH = re.compile(r'[0-9a-f]{16}')


def runtime_sources(home, roots):
    from .desktop import unlinked
    sources = {}
    for root, installation in roots:
        if not root.is_dir() or not unlinked(root): continue
        root = root.resolve()
        if root == home or root.is_relative_to(home) or home.is_relative_to(root): continue
        targets = []
        binary = root / 'bin'
        try:
            if binary.is_dir() and unlinked(binary):
                for name in EXECUTABLES:
                    if (binary / name).is_file(): targets.append('bin/' + name)
                for child in binary.iterdir():
                    if child.is_dir() and HASH.fullmatch(child.name) and unlinked(child):
                        targets.append('bin/' + child.name)
            runtime = root / 'runtimes/cua_node'
            if runtime.is_dir() and unlinked(runtime):
                targets.extend(child.relative_to(root).as_posix() for child in runtime.iterdir()
                               if child.is_dir() and HASH.fullmatch(child.name) and unlinked(child))
        except OSError: pass
        if targets:
            key = hashlib.sha256(os.path.normcase(str(root)).encode('utf-8')).hexdigest()[:20]
            sources[key] = {'root': root, 'kind': 'runtime', 'installation': installation, 'targets': sorted(targets)}
    return sources


def system_inventory():
    if os.name != 'nt': return {'complete': False}
    shell = Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
    try:
        result = subprocess.run([str(shell), '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
                                 '-File', str(Path(__file__).with_name('runtime_audit.ps1'))],
                                capture_output=True, encoding='utf-8-sig', timeout=30,
                                creationflags=subprocess.CREATE_NO_WINDOW)
        if result.returncode: return {'complete': False}
        return json.loads(result.stdout)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return {'complete': False}


def normalized(value):
    value = os.path.expandvars(str(value)).replace('/', '\\').casefold()
    for variable in ('LOCALAPPDATA', 'APPDATA', 'USERPROFILE'):
        value = re.sub(r'\$env:' + variable, lambda _: os.environ.get(variable, '').replace('/', '\\').casefold(), value, flags=re.I)
    while '\\\\' in value: value = value.replace('\\\\', '\\')
    return value.strip().strip('"\'').rstrip('\\')


def mentions(value, target):
    value, target = normalized(value), normalized(target)
    return bool(re.search(re.escape(target) + r'(?![\w.\-])', value))


def digest(path):
    # All inputs are local, known runtime files; never execute a candidate.
    with path.open('rb') as stream:
        result = hashlib.sha256()
        for block in iter(lambda: stream.read(1024 * 1024), b''): result.update(block)
        return result.hexdigest()


def fingerprint(root, names):
    result = hashlib.sha256()
    for name in names:
        result.update(name.encode()); result.update(b'\0')
        result.update(digest(root / name).encode()); result.update(b'\0')
    return result.hexdigest()[:16]


def installed_replacements(inventory, local):
    """Confirm deployed successors against the installed package, byte for byte."""
    from .desktop import unlinked
    replacements = {}
    def verify(source, deployed):
        return (source.is_file() and deployed.is_file() and unlinked(deployed)
                and source.stat().st_size == deployed.stat().st_size and digest(source) == digest(deployed))
    def verify_group(pairs):
        if all(verify(source, deployed) for source, deployed in pairs):
            for source, deployed in pairs:
                if source.name in EXECUTABLES: replacements.setdefault(source.name, []).append(deployed)
    for package in inventory.get('packages', []):
        root = Path(package.get('InstallLocation') or '') / 'app/resources'
        if not root.is_dir(): continue
        try:
            core = list(EXECUTABLES[:4])
            key = fingerprint(root, core)
            verify_group([(root / name, local / 'bin' / key / name) for name in core])
        except OSError: pass
        try:
            key = fingerprint(root, ['rg.exe'])
            verify_group([(root / 'rg.exe', local / 'bin' / key / 'rg.exe')])
        except OSError: pass
        try:
            runtime = root / 'cua_node'
            names = ['manifest.json', 'bin/node.exe', 'bin/node_repl.exe']
            key = fingerprint(runtime, names)
            deployed = local / 'runtimes/cua_node' / key
            modules = deployed / 'bin/node_modules'
            if modules.is_dir() and unlinked(modules):
                verify_group([(runtime / name, deployed / name) for name in names])
        except OSError: pass
    return replacements


def config_references(home):
    """Read current launch configuration, never conversation histories or secrets in output."""
    references, complete = [], True
    user = Path.home()
    paths = {home / 'config.toml', user / '.codex/config.toml', user / '.mcp.json',
             Path.cwd() / '.mcp.json', Path.cwd() / '.vscode/settings.json'}
    roaming = os.environ.get('APPDATA')
    if roaming:
        paths.update(Path(roaming) / name for name in ('Code/User/settings.json', 'Cursor/User/settings.json',
                                                     'Claude/claude_desktop_config.json'))
    for folder in (user / 'Documents/PowerShell', user / 'Documents/WindowsPowerShell'):
        if folder.is_dir(): paths.update(folder.glob('*profile.ps1'))
    for path in paths:
        try:
            if not path.exists(): continue
            if path.stat().st_size > 2 * 1024 * 1024: complete = False; continue
            text = path.read_text(encoding='utf-8-sig')
            references.append({'source': 'configuration', 'value': text})
            # Include directory-valued PATH/cwd settings, not just full executable paths.
            for match in re.finditer(r'"(?:\\.|[^"\\])*"|\'[^\']*\'', text):
                value = match[0][1:-1]
                if match[0].startswith('"'):
                    try: value = json.loads(match[0])
                    except ValueError: pass
                references.append({'source': 'configuration', 'value': value})
        except (OSError, UnicodeError): complete = False
    return references, complete


def audit_runtimes(home, sources, cli):
    runtime_sources = {key: source for key, source in sources.items() if source['kind'] == 'runtime'}
    if not runtime_sources: return {}
    inventory = system_inventory()
    references, complete = config_references(home)
    references = list(references)
    complete = complete and inventory.get('complete') is True
    references += inventory.get('references', [])
    references.append({'source': 'cleaner CLI', 'value': cli.get('path', '')})
    for process in inventory.get('processes', []):
        references.append({'source': 'process', 'value': process.get('ExecutablePath') or ''})
        references.append({'source': 'process arguments', 'value': process.get('CommandLine') or ''})
    local = Path(os.environ.get('LOCALAPPDATA', '')) / 'OpenAI/Codex'
    replacements = installed_replacements(inventory, local) if complete else {}
    results = {}
    for key, source in runtime_sources.items():
        for target in source['targets']:
            path = source['root'] / target
            evidence = []
            problem = ''
            try:
                files = list(path.rglob('*')) if path.is_dir() else [path]
                executables = [file for file in files if file.is_file() and file.name in EXECUTABLES]
                if target.startswith('bin/') and path.is_dir() and any(file.name not in EXECUTABLES for file in files):
                    problem = 'runtime_unverified'
                if not executables: problem = 'runtime_unverified'
                for file in executables:
                    successors = replacements.get(file.name, [])
                    if any(normalized(file) == normalized(successor) for successor in successors): problem = 'runtime_current'
                    elif not successors and not problem: problem = 'runtime_unverified'
                    if any(not p.get('ExecutablePath') and p.get('Name', '').casefold() == file.name.casefold()
                           for p in inventory.get('processes', [])) and not problem: problem = 'runtime_unknown'
                for value in inventory.get('paths', []):
                    directory = Path(value)
                    referenced = (normalized(directory) == normalized(path.parent) if path.is_file()
                                  else normalized(directory) == normalized(path) or mentions(directory, path))
                    if referenced:
                        evidence.append('PATH')
                for reference in references:
                    value = reference.get('value') or ''
                    # Flat legacy layouts share helpers. A reference to one sibling
                    # keeps the family, including sandbox setup and command runners.
                    family = (path.is_file() and any(mentions(value, path.parent / name) for name in EXECUTABLES))
                    directory_values = {normalized(part) for part in value.split(';')}
                    directory = normalized(path.parent if path.is_file() else path)
                    if (mentions(value, path) or family or directory in directory_values
                            or normalized(source['root']) in directory_values):
                        evidence.append(reference['source'])
                if evidence and problem != 'runtime_current': problem = 'runtime_referenced'
                if not complete: problem = 'runtime_unknown'
                if not problem: evidence = ['processes', 'PATH', 'startup', 'tasks', 'services', 'shortcuts', 'configuration', 'verified replacement']
            except (OSError, ValueError):
                problem = 'runtime_unknown'
            results[(key, target)] = {'reason': problem, 'checks': sorted(set(evidence))}
    return results
