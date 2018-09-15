import class_key
import collections
import flask
import functools
import inspect
import itertools
import more_itertools

@class_key.class_key()
class ViewFuncNode:
    def __init__(self, view, parent=None, *, name=None, display_string=None, var_name=None, var_converter=None, iterable=None, redirect_func=None):
        self.view = view
        self.parent = parent
        self.children = collections.OrderedDict()
        self.name = name
        self.display_string = display_string
        self.var_name = var_name
        self.var_converter = var_converter
        self.iterable = iterable
        self.redirect_func = redirect_func

    @property
    def __key__(self):
        return (() if self.is_index else self.parent.__key__) + (self.name,)

    @property
    def children_are_static(self):
        return isinstance(self.children, dict)

    @property
    def is_index(self):
        return self.parent is None

    @property
    def is_redirect(self):
        return self.redirect_func is not None

    @property
    def is_static(self):
        return self.is_index or self.parent.children_are_static

    @property
    def parents(self):
        if self.is_index:
            return []
        else:
            return [self.parent] + self.parent.parents

    def register(self, app, options):
        def child(name, display_string=None, **options):
            def decorator(f):
                @functools.wraps(f)
                def wrapper(**kwargs):
                    flask.g.view_node = ViewNode(wrapper.view_func_node, kwargs)
                    return f(**flask.g.view_node.kwargs)

                wrapper.view_func_node = ViewFuncNode(wrapper, self, name=name, display_string=display_string)
                self.children[name] = wrapper.view_func_node
                wrapper.view_func_node.register(app, options)
                return wrapper

            return decorator

        def redirect(name, display_string=None, **options):
            def decorator(f):
                @functools.wraps(f)
                def wrapper(**kwargs):
                    target_node = ViewNode(self, kwargs).resolve_redirect()
                    return flask.redirect(target_node.url)

                def redirect_children_view_func(flask_view_tree_redirect_subtree, **kwargs):
                    target_node = ViewNode(self, kwargs).resolve_redirect()
                    return flask.redirect('{}/{}'.format(target_node.url, flask_view_tree_redirect_subtree))

                wrapper.view_func_node = ViewFuncNode(wrapper, self, name=name, display_string=display_string, redirect_func=f)
                app.add_url_rule(wrapper.view_func_node.url_rule, f.__name__, wrapper, **options)
                app.add_url_rule('{}/<path:flask_view_tree_redirect_subtree>'.format(wrapper.view_func_node.url_rule), 'flask_view_tree_redirect_children_{}'.format(f.__name__), redirect_children_view_func, **options)
                return wrapper

            return decorator

        def children(var_converter=identity, iterable=None, **options):
            def decorator(f):
                @functools.wraps(f)
                def wrapper(**kwargs):
                    flask.g.view_node = ViewNode(wrapper.view_func_node, kwargs)
                    return f(**flask.g.view_node.kwargs)

                child_var = more_itertools.one(set(inspect.signature(f).parameters) - set(self.variables)) # find the name of the parameter that the child's viewfunc has but self's doesn't
                wrapper.view_func_node = ViewFuncNode(wrapper, self, var_name=child_var, var_converter=var_converter, iterable=iterable)
                self.children = wrapper.view_func_node
                wrapper.view_func_node.register(app, options)
                return wrapper

            return decorator

        app.add_url_rule(self.url_rule, self.view.__name__, self.view, **options)
        self.view.child = child
        self.view.redirect = redirect
        self.view.children = children

    @property
    def url_rule(self):
        if self.is_index:
            return '/'
        elif self.is_static:
            return '{}/{}'.format('' if self.parent.is_index else self.parent.url_rule, self.name)
        else:
            return '{}/<{}>'.format('' if self.parent.is_index else self.parent.url_rule, self.var_name)

    @property
    def variables(self):
        if self.is_index:
            return collections.OrderedDict()
        elif self.is_static:
            return self.parent.variables
        else:
            return collections.OrderedDict(itertools.chain(self.parent.variables, [(self.var_name, self.var_converter)]))

@class_key.class_key()
class ViewNode:
    def __init__(self, view_func_node, raw_kwargs, *, kwargs=None):
        self.view_func_node = view_func_node
        self.raw_kwargs = raw_kwargs
        for attr in {'children_are_static', 'is_index', 'is_redirect', 'is_static', 'variables', 'view'}:
            setattr(self, attr, getattr(self.view_func_node, attr))
        if kwargs is None:
            self.kwargs = {}
            for variable, converter in self.variables.items():
                if variable in inspect.signature(converter).parameters:
                    self.kwargs[variable] = converter(**{
                        self.kwargs.get(iter_var, self.raw_kwargs[iter_var])
                        for iter_var in self.variables
                        if iter_var in inspect.signature(converter).parameters
                    })
                else:
                    # variable name doesn't appear in converter's kwargs, assume it takes a single positional argument
                    self.kwargs[variable] = converter(self.raw_kwargs[variable])
        else:
            self.kwargs = kwargs

    @property
    def __key__(self):
        return (() if self.is_index else self.parent.__key__) + (self.view_func_node.name if self.is_static else self.var,)

    @staticmethod
    def url_part(view_func_node, kwarg_value):
        if view_func_node.is_static:
            return view_func_node.name
        else:
            if hasattr(kwarg_value, 'url_part'):
                return kwarg_value.url_part
            else:
                return str(kwarg_value)

    def __str__(self):
        if self.is_index:
            return '/'
        elif self.is_static:
            if self.view_func_node.display_string is None:
                return self.view_func_node.name
            else:
                return self.view_func_node.display_string
        else:
            return str(self.arg)

    def __truediv__(self, other):
        if self.children_are_static:
            return more_itertools.one(
                child
                for child in self.children
                if child.view_func_node.name == other
            )
        else:
            child_node = self.view_func_node.children
            return ViewNode(child_node, {child_node.var_name: ViewNode.url_part(child_node, other), **self.raw_kwargs}, kwargs={child_node.var_name: other, **self.kwargs})

    @property
    def children(self):
        if self.children_are_static:
            return [
                ViewNode(child_node, self.raw_kwargs, kwargs=self.kwargs)
                for child_node in self.view_func_node.children.values()
            ]
        else:
            child_node = self.view_func_node.children
            if self.view_func_node.iterable is None:
                children_iter = iter(child_node.var_converter)
            else:
                children_iter = iter(child_node.iterable)
            return [
                ViewNode(child_node, {child_node.var_name: ViewNode.url_part(child_node, var_value), **self.raw_kwargs}, kwargs={child_node.var_name: var_value, **self.kwargs})
                for var_value in children_iter
            ]

    @property
    def parent(self):
        if self.is_index:
            return None
        else:
            parent_raw_kwargs = {
                arg_name: arg_val
                for arg_name, arg_val in self.raw_kwargs.items()
                if arg_name != self.view_func_node.var_name
            }
            parent_kwargs = {
                arg_name: arg_val
                for arg_name, arg_val in self.kwargs.items()
                if arg_name != self.view_func_node.var_name
            }
            return ViewNode(self.view_func_node.parent, parent_raw_kwargs, kwargs=parent_kwargs)

    @property
    def parents(self):
        if self.is_index:
            return []
        else:
            return [self.parent] + self.parent.parents

    def resolve_redirect(self):
        target_node = self
        for target_part in self.view_func_node.redirect_func(**self.raw_kwargs):
            target_node = target_node.with_redirect_target_part(target_part)
        return target_node

    @property
    def url(self):
        return flask.url_for(self.view.__name__, **self.raw_kwargs)

    @property
    def var(self):
        return self.kwargs[self.view_func_node.var_name]

    def with_redirect_target_part(self, target_part):
        if hasattr(target_part, 'view_func_node'):
            target_part = target_part.view_func_node
        if isinstance(target_part, ViewFuncNode):
            target_part = ViewNode(target_part, self.raw_kwargs, kwargs=self.kwargs)
        if isinstance(target_part, ViewNode):
            while target_part.is_redirect:
                target_part = target_part.resolve_redirect()
            return target_part
        return self / target_part

def identity(x):
    return x

def index(app, **options):
    def decorator(f):
        @functools.wraps(f)
        def wrapper(**kwargs):
            flask.g.view_node = ViewNode(wrapper.view_func_node, kwargs)
            return f(**flask.g.view_node.kwargs)

        wrapper.view_func_node = ViewFuncNode(wrapper)
        wrapper.view_func_node.register(app, options)
        return wrapper

    return decorator
