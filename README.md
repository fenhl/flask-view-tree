**flask-view-tree** is a utility for hierarchically structuring webpages in [Flask](http://flask.pocoo.org/).

# Dependencies

* Python 3.5
* [class_key](https://github.com/fenhl/python-class-key)
* [more_itertools](https://pypi.org/project/more-itertools/)

# Example

```python
import flask
import flask_view_tree

import my_app.model

app = application = flask.Flask(...)

@flask_view_tree.index(app) # The entry point to the flask_view_tree API. Registers this view function for `/`.
def index():
    return flask.render_template('index.html')

@index.child('users') # Registers this view function for `/users`.
def users_list():
    return flask.render_template('users-list.html')

@users_list.children(my_app.model.User) # Registers this view function for `/users/<user>`.
def profile(user):
    return flask.render_template('profile.html', user=user) # `user` will be the result of calling `my_app.model.User` with the given URL fragment.

@index.redirect('me') # Redirects `/me` to `/users/<flask.g.user>`, and all URLs starting with `/me/` to `/users/<flask.g.user>/`.
def me():
    return profile, flask.g.user
```

**Note:** A node can either have any number of children registered using `child`, or have all children handled by a single registration of `children`. Do not mix `child` and `children`, or call `children` multiple times on the same node, unless you're sure you know what you're doing.

A view function decorated using `children` has a `viewfunc.catch_init` property which can decorate an exception handler. This handler will be called if converting the variable fails and one of the given exception types is raised, passing the caught exception as well as the raw argument value. It can be used multiple times to handle different kinds of exceptions differently.

```python
@profile.catch_init(KeyError, FileNotFoundError)
def profile_catch_init(exc, value):
    return flask.render_template('user_not_found.html', username=value), 404

@profile.catch_init(ValueError)
def profile_catch_init(exc, value):
    return flask.render_template('invalid_username.html', username=value), 404
```
