"""Collect runtime-selected SciPy NumPy compatibility modules, not other backends."""
from importlib.util import find_spec


def scipy_hidden_imports():
    from PyInstaller.utils.hooks import collect_submodules
    hidden = set()
    found = False
    # SciPy releases have used both locations. Do not hardcode only the one
    # installed on the developer's PC (the report used _external).
    for parent in ('scipy._external', 'scipy._lib'):
        root = parent + '.array_api_compat'
        try:
            present = find_spec(root)
        except ModuleNotFoundError as exc:
            if exc.name not in (parent, root):
                raise
            present = None
        if present is None:
            continue
        found = True
        hidden.add(root)
        for branch in ('numpy', 'common'):
            package = root + '.' + branch
            modules = collect_submodules(package, on_error='raise')
            if not modules:
                raise RuntimeError('Missing SciPy runtime package: ' + package)
            hidden.update(modules)
        for leaf in ('fft', 'linalg'):
            if root + '.numpy.' + leaf not in hidden:
                raise RuntimeError('Incomplete SciPy NumPy backend: ' + leaf)
    if not found:
        raise RuntimeError('SciPy array_api_compat was not found; review this SciPy release before packaging')
    return sorted(hidden)
