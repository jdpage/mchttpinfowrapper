"""A web UI for managing a Minecraft server
"""

# Copyright (C) 2015  Jonathan David Page
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

from flask import Flask, request, session, g, redirect, url_for, abort, \
    render_template, flash
app = Flask(__name__)

@app.route('/login', methods=['GET', 'POST'])
def login():
    return render_template('login.html', error=None)

@app.route('/')
def hello_world():
    return 'Hello world'
