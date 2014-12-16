import datetime
import time

from protorpc import messages
from protorpc import message_types
from protorpc import remote
from pickle import dumps, loads
from google.appengine.api import users

import main

class Comment(messages.Message):
    article_id = messages.IntegerField(1, required=True)
    comment_text = messages.StringField(2, required=True)

class Comments(messages.Message):
    comments = messages.MessageField(comment, 1, repeated=True)

class GetCommentsRequest(messages.Message):
    limit = messages.IntegerField(1, default=10)

class ArchiveService(remote.Service):
    # Add the remote decorator to indicate the service methods
    @remote.method(Nomment, message_types.VoidMessage)
    def post_comment(self, request):
      article = Articles(parent=archive_key()).get_by_id(request.article_id, parent=archive_key())
      pickled = db.Text(dumps([request.comment_text), users.get_current_user(), datetime.now()]))
      article.comments.append(pickled)
      article.put()
      return message_types.VoidMessage()
        
    @remote.method(GetCommentsRequest, Commments)
    def get_comments(self, request):
      for comment in main.Articles.get_by_id(request.article_id, parent=main.archive_key()).comments
        loads(comment)
#structure the return
        return "not implemented - incomplete stub"

