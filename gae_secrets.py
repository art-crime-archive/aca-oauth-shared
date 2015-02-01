''' 
This module creates entities in the datastore for secrets that should not be
placed in source code repositories.

Creates a Secret entity in the dataStore for each provider if one does not
already exist. New providers must have their Secret entities updated manually
using the edit entity feature of the App Engine developer console
'''
import os
import base64
from google.appengine.ext import ndb
from config import CONFIG
import logging

class AdminUser(ndb.Model):
	provider = ndb.StringProperty()
	name = ndb.StringProperty()

def newAdminUser(provider):
	return AdminUser(parent=akey, provider=provider, name='admin')

akey = ndb.Key('AdminUser', 'admin_users')
admin_query = AdminUser.query(ancestor=akey)
admins = admin_query.fetch()
storedAdmins = {a.provider: {'name':a.name} for a in admins}

class Secret(ndb.Model):
    """Models an individual Secret entry."""
    provider = ndb.StringProperty()
    consumer_key = ndb.StringProperty()
    consumer_secret = ndb.StringProperty()

def newSecret(provider):
    return Secret(parent=key, provider=provider, consumer_key='k', consumer_secret='s')

key = ndb.Key('Secrets', 'client_secrets')
secrets_query = Secret.query(ancestor=key)
secrets = secrets_query.fetch()
storedProviders = {s.provider: {'consumer_key':s.consumer_key, 'consumer_secret':s.consumer_secret} for s in secrets}

ndb.put_multi(newSecret(p) for p in CONFIG if p not in storedProviders)

if 'salt' not in storedProviders:
  random32 = Secret(parent=key, provider='salt', consumer_key='k', 
                    consumer_secret=base64.b64encode(os.urandom(32)))
  ndb.put_multi([random32])


#update CONFIG with stored secrets
for provider in CONFIG:
    try:
        CONFIG[provider]['consumer_key'] = storedProviders[provider]['consumer_key']
        CONFIG[provider]['consumer_secret'] = storedProviders[provider]['consumer_secret']
    except KeyError:
        logging.info("The secrets for new provider %s may not have been updated", provider)

CONFIG['salt'] = {'consumer_secret': storedProviders['salt']['consumer_secret']}
