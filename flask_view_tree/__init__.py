import flask
import functools
import inspect
import more_itertools

class ViewFuncNode:
    def __init__(self, view, parent=None, *, name=None, display_string=None, var_name=None, var_converter=None, iterable=None):
        self.view = view
        self.parent = parent
        self.children = {}
        self.name = name
        self.display_string = display_string
        self.var_name = var_name
        self.var_converter = var_converter
        self.iterable = iterable

    @property
    def children_are_static(self):
        return isinstance(self.children, dict)

    @property
    def is_index(self):
        return self.parent is None

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

        def children(var_converter, iterable=None, **options):
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
            return {}
        elif self.is_static:
            return self.parent.variables
        else:
            return {self.var_name: self.var_converter, **self.parent.variables}

class ViewNode:
    def __init__(self, view_func_node, raw_kwargs, *, kwargs=None):
        self.view_func_node = view_func_node
        self.raw_kwargs = raw_kwargs
        for attr in {'children_are_static', 'is_index', 'is_static', 'variables', 'view'}:
            setattr(self, attr, getattr(self.view_func_node, attr))
        if kwargs is None:
            self.kwargs = {
                variable: converter(self.raw_kwargs[variable])
                for variable, converter in self.variables
            }
        else:
            self.kwargs = kwargs

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

    @property
    def url(self):
        return flask.url_for(self.view.__name__, **self.raw_kwargs)

    @property
    def var(self):
        return self.kwargs[self.view_func_node.var_name]

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
