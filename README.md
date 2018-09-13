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

@index.child('users') # Registers this view function for `/about`.
def users_list():
    return flask.render_template('users-list.html')

@users_list.children(my_app.model.User) # Registers this view function for `/users/<user>`.
def profile(user):
    return flask.render_template('profile.html')
```

**Note:** A node can either have any number of children registered using `child`, or have all children handled by a single registration of `children`. Do not mix `child` and `children`, or call `children` multiple times on the same node, unless you're sure you know what you're doing.
