"""Preserve function defaults.

Preserve the default argument values of function signatures in source code
and keep them not evaluated for readability.
"""

import ast
import inspect
import sys
from typing import Any, Dict, List, Optional

from sphinx.application import Sphinx
from sphinx.locale import __
from sphinx.pycode.ast import parse as ast_parse
from sphinx.pycode.ast import unparse as ast_unparse
from sphinx.util import logging

logger = logging.getLogger(__name__)


class DefaultValue:
    def __init__(self, name: str) -> None:
        self.name = name

    def __repr__(self) -> str:
        return self.name


def get_function_def(obj: Any) -> ast.FunctionDef:
    """Get FunctionDef object from living object.
    This tries to parse original code for living object and returns
    AST node for given *obj*.
    """
    try:
        source = inspect.getsource(obj)
        if source.startswith((' ', r'\t')):
            # subject is placed inside class or block.  To read its docstring,
            # this adds if-block before the declaration.
            module = ast_parse('if True:\n' + source)
            return module.body[0].body[0]  # type: ignore
        else:
            module = ast_parse(source)
            return module.body[0]  # type: ignore
    except (OSError, TypeError):  # failed to load source code
        return None


def get_default_value(lines: List[str], position: ast.AST) -> Optional[str]:
    try:
        if sys.version_info < (3, 8):  # only for py38+
            return None
        elif position.lineno == position.end_lineno:
            line = lines[position.lineno - 1]
            return line[position.col_offset:position.end_col_offset]
        else:
            # multiline value is not supported now
            return None
    except (AttributeError, IndexError):
        return None


def update_defvalue(app: Sphinx, obj: Any, bound_method: bool) -> None:
    """Update defvalue info of *obj* using type_comments."""
    if not app.config.autodoc_preserve_defaults:
        return

    try:
        lines = inspect.getsource(obj).splitlines()
        if lines[0].startswith((' ', r'\t')):
            lines.insert(0, '')  # insert a dummy line to follow what get_function_def() does.
    except (OSError, TypeError):
        lines = []

    try:
        function = get_function_def(obj)
        if function.args.defaults:
            defaults = list(function.args.defaults)
        else:
            defaults = [None] * len(function.args.args)

        if hasattr(function.args, 'kw_defaults') and function.args.kw_defaults is not None:
            kw_defaults = list(function.args.kw_defaults)
        else:
            kw_defaults = [None] * len(function.args.kwonlyargs)
        if function.args.kw_defaults:
            kw_defaults = list(function.args.kw_defaults)
        else:
            kw_defaults = [None] * len(function.args.kwonlyargs)
        if defaults or kw_defaults:
            sig = inspect.signature(obj)
            parameters = list(sig.parameters.values())
            for i, param in enumerate(parameters):
                if param.default is not param.empty:
                    if param.kind in (param.POSITIONAL_ONLY, param.POSITIONAL_OR_KEYWORD) and defaults[0] is not None:
                        default = defaults.pop(0)
                        value = get_default_value(lines, default)
                        if value is None and default is not None:
                            value = ast_unparse(default)  # type: ignore
                        parameters[i] = param.replace(default=DefaultValue(value))
                    elif param.kind == param.KEYWORD_ONLY:
                        default = kw_defaults.pop(0)
                        if default is not None:
                            value = get_default_value(lines, default)
                            if value is None:
                                value = ast_unparse(default)  # type: ignore
                            parameters[i] = param.replace(default=DefaultValue(value))
            obj.__signature__ = sig.replace(parameters=parameters)
    except (AttributeError, TypeError) as exc:
        logger.warning(__("Failed to update signature for %r: %s"), obj, exc)
    except NotImplementedError as exc:
        logger.warning(__("Failed to parse a default argument value for %r: %s"), obj, exc)


def setup(app: Sphinx) -> Dict[str, Any]:
    app.add_config_value('autodoc_preserve_defaults', False, True)
    app.connect('autodoc-before-process-signature', update_defvalue)

    return {
        'version': '1.0',
        'parallel_read_safe': True
    }
