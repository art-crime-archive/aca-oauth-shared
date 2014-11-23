.. |pyopenid| replace:: python-openid
.. _pyopenid: http://pypi.python.org/pypi/python-openid/

==================
Authomatic for GAE
==================

Authomatic
is an **authorization/authentication**
client library for Python web applications
created by Peter Hudec
For more info visit the project page at http://peterhudec.github.io/authomatic.

Features
========

* Uses the DataStore for provider secrets instead of config.py
* authomatic and openid modeules included so it works out of the box

License and Requirements
========================

The Authomatic package is licensed under
`MIT license <http://en.wikipedia.org/wiki/MIT_License>`__
and requires **Python 2.6** and higher, but doesn't support **Python 3** yet.

The |pyopenid|_ package is licensed under Apache.

Usage
=====

Clone this archive and add the app to app engine launcher.  Run it locally or 
deploy it to App Engine and then use the edit entity feature of the App Engine
developer console to  manually update a providers Secret entities

Read the exhaustive documentation at http://peterhudec.github.io/authomatic.
