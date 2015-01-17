import logging
import main
from google.appengine.ext import deferred
from google.appengine.runtime import DeadlineExceededError
from google.appengine.ext import db
from config import CONFIG

BATCH_SIZE = 100  # ideal batch size may vary based on entity size.

def UpdateSchema(cursor=None, num_updated=0):
	query = main.Articles.all()
	defaultList = ['gg','fb','tw']
	if cursor:
		query.with_cursor(cursor)
	to_put = []
	for p in query.fetch(limit=BATCH_SIZE):
		if p.provider not in CONFIG:
			p.provider = defaultList[0]
		to_put.append(p)

	if to_put:
		db.put(to_put)
		num_updated += len(to_put)
		logging.info('Put %d entities to Datastore for a total of %d',len(to_put), num_updated)
		deferred.defer(UpdateSchema, cursor=query.cursor(), num_updated=num_updated)
	else:
		logging.info('UpdateSchema complete with %d updates!', num_updated)