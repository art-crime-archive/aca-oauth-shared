#
# Copyright 2012 Dan Salmonsen
#
# todo - create single page template that works for all site URLS
# todo - active link set by javascript based on page URL
# todo - History.js based navigation
# todo - hide / show relevent content
# scroll / multi-page load
# unique URL for each article
# check user before allowing edit of form.

from protorpc.wsgi import service
import webapp2, os, json, logging, urllib
from google.appengine.ext import ndb
from google.appengine.ext.webapp import template
from google.appengine.api import urlfetch, users
from google.appengine.ext import db
from datetime import datetime, timedelta
from dateutil import parser
from random import randint
from re import sub
from lxml import etree, html
from lxml.html import tostring, fragment_fromstring
from pickle import dumps, loads

from authomatic import Authomatic
from authomatic.adapters import Webapp2Adapter
from config import CONFIG

authomatic = Authomatic(config=CONFIG, secret='some random secret string')

class Login(webapp2.RequestHandler):
    
    # The handler must accept GET and POST http methods and
    # Accept any HTTP method and catch the "provider_name" URL variable.
    def any(self, provider_name):
                
        # It all begins with login.
        result = authomatic.login(Webapp2Adapter(self), provider_name)
        
        # Do not write anything to the response if there is no result!
        if result:
            if result.user:
                result.user.update()
                if result.user.name:
                     self.response.write('<h1>Hi {0}</h1>'.format(result.user.name))
                
                     # Save the user name and ID to cookies that we can use it in other handlers.
                     self.response.set_cookie('user_id', result.user.id)
                     self.response.set_cookie('user_name', urllib.quote(result.user.name))
                     self.response.set_cookie('user_email', result.user.email)
                     self.response.set_cookie('user_provider', provider_name)
                
                     if result.user.credentials:
                         # Serialize credentials and store it as well.
                         serialized_credentials = result.user.credentials.serialize()
                         self.response.set_cookie('credentials', serialized_credentials)
                     self.response.delete_cookie('error')
                else:
                     self.response.set_cookie('error', "Missing User Name!")
            elif result.error:
                self.response.set_cookie('error', urllib.quote(result.error.message))
            
            self.redirect('/')


class Logout(webapp2.RequestHandler):
    def get(self):
        # Delete cookies.
        self.response.delete_cookie('user_id')
        self.response.delete_cookie('user_name')
        self.response.delete_cookie('user_email')
        self.response.delete_cookie('credentials')
        self.response.delete_cookie('error')
        
        # Redirect home.
        #self.redirect('./')
        self.redirect('/auth')
		
                # Welcome the user.
                # self.response.write(u'<h1>Hi {}</h1>'.format(result.user.name))
                # self.response.write(u'<h2>Your id is: {}</h2>'.format(result.user.id))
                # self.response.write(u'<h2>Your email is: {}</h2>'.format(result.user.email))

class Articles(db.Model):
  """Models an individual Archive entry"""
  author = db.StringProperty()
  embed = db.TextProperty()
  title = db.StringProperty()
  content = db.TextProperty()
  tags = db.TextProperty()
  comments = db.ListProperty(db.Text)
  view = db.StringProperty() #Publish, Preview or Retract
  provider = db.StringProperty() #Source (Facebook, Twitter...etc)
  date = db.DateTimeProperty(auto_now_add=True)

def archive_key(Archive_name=None):
  """Constructs a Datastore key for an Archive entity."""
  return db.Key.from_path('Archive', Archive_name or 'test_archive')
  
def innerHTML(file, tag):
  tree = html.parse(file)
  return ''.join([tostring(child) for child in tree.xpath(tag)[0].iterchildren()])

def format_comments(comments=None, article_id=None):
  template_data = {
          'user_activity': '',
          'article_id': article_id,}
  comment_box = ('<form class="comment-form" name="comment-form" action="/comment-on?id=%s" method="post">'
                  '<textarea class="comment-text" name="comment-text" title="add your comment..."></textarea>'
                  '</form>' % article_id)
#todo - build comment tree by replacing and adding.
#todo - add report abuse.
  path = os.path.join(os.path.dirname(__file__), 'comment-table-template.html' )
  all_comments = '<div class="below-video comments">Comments:<table>'
  template_data.update({'comment_id': len(comments)})
  tree = fragment_fromstring(template.render(path, template_data), create_parent=False)
  all_comments += tostring(tree.xpath('//tfoot')[0])#needs better element addressing
  all_comments += '<tbody id="comment-table-' + str(article_id) + '">'
  comment_id = 0
  for comment in comments:
    nickname = str(loads(str(comment))[1]).split('@',2)[0]
    template_data.update({
        'comment_id': str(comment_id),
        'comment_display': loads(str(comment))[0],
        'nickname': nickname,
        'comment_date': loads(str(comment))[2],
        'time_now': datetime.now()
        })
    tree = fragment_fromstring(template.render(path, template_data), create_parent=False)
    if nickname != '':
      all_comments += tostring(tree.xpath('//tr')[1])
    else:
      all_comments += tostring(tree.xpath('//tr')[2]) #deleted comment tr
    comment_id += 1
    
  #place an empty hidden comment last
  template_data.update({'comment_id': len(comments)})
  tree = fragment_fromstring(template.render(path, template_data), create_parent=False)
  all_comments += tostring(tree.xpath('//tr')[3]) #hidden comment tr
  all_comments += '</tbody></table></div>'
  return all_comments

def format_article(article, all_articles):
    edit_link = ''
    view_status = ''
    if str(users.get_current_user()) == article.author:
      edit_link = '<a class="links" href="/edit-article-form?id=%s">edit</a>' % article.key().id()
      if article.view != 'Publish':
         view_status = '<a class="view-status" href="/edit-article-form?id=%s">not published</a>' % (article.key().id())
    #todo - move to article template file
    all_articles += '<div class="embed">%s</div>' % article.embed
    all_articles += '<div class="title"> <a class="article-link no-ajax" href="/article?id=%s">%s</a> ' % (article.key().id(), article.title)
    all_articles += '<span class="author"> by %s </span>' % article.author.split('@',2)[0]
    all_articles += '<span> %s %s </span></div>' % (view_status, edit_link)
    all_articles += '<div class="below-video article"><pre>%s</pre></div>' % article.content
    all_articles += '<div class="below-video tags">Tags: %s</div>' % article.tags
    all_articles += format_comments(article.comments, article.key().id())
    return all_articles
	
def get_articles(id=None, author=None, limit=None, bookmark=None, provider=None):
  """Retrieves articles from Archive entity and composes HTML."""
  if not limit:
    limit = 10

  articles = Articles().all().order("-date")

  if author:
    articles = articles.filter('author =', author)
#Prevent clashes
  if provider:
    articles = articles.filter('provider =', provider)

  next = None
  if bookmark:
    articles = articles.filter('date <=', parser.parse(bookmark)).fetch(limit + 1)
  else:
    articles = articles.fetch(limit + 1)
    
  if len(articles) == limit + 1:
    next = str(articles[-1].date)
  articles = articles[:limit]

  all_articles =''
  for article in articles:
    all_articles = format_article(article, all_articles)

  if next:
    all_articles += '<div class="bookmark" data-bookmark="%s" ></div>' % next
  else:
    all_articles += '<div class="bookmark-end">No more articles.</div>'
  return all_articles

class TestPage(webapp2.RequestHandler):
  pass
# test page stub

class MainPage(webapp2.RequestHandler):
  def get(self):
    style = ''
    #user = users.get_current_user()
	
	#Pull user data from cookies
    serialized_credentials = self.request.cookies.get('credentials')
    user_id = self.request.cookies.get('user_id')
    user_name = urllib.unquote(self.request.cookies.get('user_name', ''))
    user_provider = self.request.cookies.get('user_provider')
    error = urllib.unquote(self.request.cookies.get('error', ''))
	
    #Checking cookies for login info
    if error:
      greeting = 'Sign in with: <a id="not-signed-in" class="sign-in" href="/auth">Login</a>'
      nickname = ''
    elif user_id:
      nickname = user_name
      greeting = ('<div class="signed-in" nickname="%s"> %s <a class="sign-out" href="%s">(sign out)</a></div>' % (nickname, nickname, "/logout"))
    else:
      greeting = 'Sign in with: <a id="not-signed-in" class="sign-in" href="/auth">Login</a>'
      nickname = ''

    content = 'No content for this URL'
    content_id =  self.request.path[1:]

    if self.request.get('bookmark'):
      content_id += '-next'
     
    if self.request.path == '/':
      return self.redirect('/the-archive')
      
    if self.request.path == '/article':
      content = format_article(Articles().get_by_id(int(self.request.get('id')), parent=archive_key()), '')
	
	#Should be dynamic?
    if self.request.path[:12] == '/the-archive':
      for id in open('archive-list.txt', 'r').read().split():
	    content += format_article(Articles().get_by_id(id, parent=archive_key()), '')
                             
    if self.request.path[:12] == '/recent':
      content = get_articles(limit = self.request.get('limit'),
                             bookmark = self.request.get('bookmark'))
                             
    elif self.request.path == '/test':
	  content = ''
    elif self.request.path[:12] == '/my-articles':
      if nickname != '':
        content = get_articles(author = nickname,
		                       provider = user_provider,
                               limit = self.request.get('limit'),
                               bookmark = self.request.get('bookmark'))
      else:
        if 'X-Requested-With' in self.request.headers:
          return self.error(500)
        else:
          return self.redirect('/auth')
        
    elif self.request.path == '/about':
      tree = html.parse('About-the-Art-Crime-Archive.html')
      style = tostring(tree.xpath('//style')[0])
      content = innerHTML('About-the-Art-Crime-Archive.html', 'body')
	  
    elif self.request.path == '/auth':
      content = innerHTML('loginforms.html', 'body')
	
    elif self.request.path == '/logout':
      self.response.delete_cookie('user_id')
      self.response.delete_cookie('user_name')
      self.response.delete_cookie('user_email')
      self.response.delete_cookie('credentials')
      self.response.delete_cookie('user_provider')
      self.response.delete_cookie('error')
      
	  #change to logged out look
      greeting = 'Sign in with: <a id="not-signed-in" class="sign-in" href="/auth">Login</a>'
      nickname = ''
      content = '<div>Success! You have signed off, we will log you out when you leave the site</div>'
      content += innerHTML('loginforms.html', 'body')
  
    template_data = {
            'content_id': content_id,
            'content': content,
            'nickname': nickname,
            'greeting': greeting,
            'style': style,
            }

    path = os.path.join(os.path.dirname(__file__), 'index.html' )
    self.response.headers['X-XSS-Protection'] = '0' #prevents blank embed after post
    self.response.out.write(template.render(path, template_data))

class CreateArticleForm(webapp2.RequestHandler):
  def get(self):
    #user = users.get_current_user()
    #Pull user data from cookies
    serialized_credentials = self.request.cookies.get('credentials')
    user_id = self.request.cookies.get('user_id')
    user_name = urllib.unquote(self.request.cookies.get('user_name', ''))
    error = urllib.unquote(self.request.cookies.get('error', ''))
	
    #Checking cookies for login info
    if error:
      greeting = 'Sign in with: <a id="not-signed-in" class="sign-in" href="/auth">Login</a>'
      nickname = ''
    elif user_id:
      nickname = user_name
      greeting = ('<div class="signed-in" nickname="%s"> %s <a class="sign-out" href="%s">(sign out)</a></div>' % (nickname, nickname, "/logout"))
    else:
      greeting = 'Sign in with: <a id="not-signed-in" class="sign-in" href="/auth">Login</a>'
      nickname = ''
	
    if nickname == '':
      if 'X-Requested-With' in self.request.headers:
        return self.error(500)
      else:
        return self.redirect('/auth')
      
    self.response.out.write("""
          <div id="%s" class="center-stage">
          <form action="/publish-it" method="post">
            <div>Embed-code<br /><textarea name="embed-code" rows="6" cols="auto"  class="boxsizingBorder"></textarea></div>
            <div><input type="hidden"></div>
            <div>Title<br /><textarea name="title" rows="1" cols="80"></textarea></div>
            <div><input type="hidden"></div>
            <div>Article body<br /><textarea name="content" rows="12" cols="80"></textarea></div>
            <div>Tags<br /><textarea name="tags" rows="1" cols="80"></textarea></div>
            <div><input type="submit" name="view" value="Preview"></div>
          </form>
          </div>
          """ % self.request.path[1:])


class PublishArticle(webapp2.RequestHandler):
  def post(self):
    #Pull user data from cookies
    serialized_credentials = self.request.cookies.get('credentials')
    user_id = self.request.cookies.get('user_id')
    user_name = urllib.unquote(self.request.cookies.get('user_name', ''))
    error = urllib.unquote(self.request.cookies.get('error', ''))
	
    if self.request.get('id') is not '':
      article_id = int(self.request.get('id'))
      article = Articles(parent=archive_key()).get_by_id(article_id, parent=archive_key())
    else:
      article = Articles(parent=archive_key())
    #must be logged in so the author must be
    article.author = user_name #users.get_current_user().nickname()
    article.embed = self.request.get('embed-code')
    article.title = self.request.get('title')
    article.content = self.request.get('content')
    article.tags = self.request.get('tags')
    article.view = self.request.get('view')
    article.put()
    if article.view == 'Preview' or article.view == 'Retract':
      return self.redirect('/my-articles')
    return self.redirect('/')

class EditArticleForm(webapp2.RequestHandler):
  def get(self):
    article_id = int(self.request.get('id'))
    article = Articles(parent=archive_key()).get_by_id(article_id, parent=archive_key())
    
    #user = users.get_current_user()
    #if not user:
    #  return self.redirect('/auth')
	
	#pull user info
    serialized_credentials = self.request.cookies.get('credentials')
    user_id = self.request.cookies.get('user_id')
    user_name = urllib.unquote(self.request.cookies.get('user_name', ''))
    error = urllib.unquote(self.request.cookies.get('error', ''))
	
	#check login
    if error:
      greeting = 'Sign in with: <a id="not-signed-in" class="sign-in" href="/auth">Login</a>'
      nickname = ''
    elif user_id:
      nickname = user_name
      greeting = ('<div class="signed-in" nickname="%s"> %s <a class="sign-out" href="%s">(sign out)</a></div>' % (nickname, nickname, "/logout"))
    else:
      greeting = 'Sign in with: <a id="not-signed-in" class="sign-in" href="/auth">Login</a>'
      nickname = ''
	
    if nickname == '':
        return self.redirect('/auth')
	
    self.response.out.write("""
        <div id="%s-id-%s" class="center-stage">
          <form action="/publish-it?id=%s" method="post">
            <div>Embed<br /><textarea name="embed-code" rows="6" cols="80">%s</textarea></div>
            <div><input type="hidden"></div>
            <div>Title<br /><textarea name="title" rows="1" cols="80">%s</textarea></div>
            <div><input type="hidden"></div>
            <div>Article body<br /><textarea name="content" rows="12" cols="80">%s</textarea></div>
            <div>Tags<br /><textarea name="tags" rows="1" cols="80">%s</textarea></div>
            <div><input type="submit" name="view" value="Preview">
            <input type="submit" name="view" value="Retract">
            <input type="submit" name="view" value="Publish"></div>
          </form>
        </div>  
          """ % (self.request.path[1:], article_id, article_id, article.embed, article.title, 
                 sub('<[^>]*>', '', article.content), article.tags))

app = webapp2.WSGIApplication([('/', MainPage),
                               ('/article', MainPage), 
                               ('/the-archive', MainPage), 
                               ('/the-archive-next', MainPage), 
                               ('/recent', MainPage), 
                               ('/recent-next', MainPage), 
                               ('/my-articles', MainPage), 
                               ('/my-articles-next', MainPage), 
                               ('/about', MainPage), 
                               ('/create-article', CreateArticleForm),
                               ('/edit-article-form', EditArticleForm),
                               ('/test', MainPage),
							   ('/auth', MainPage),
                               ('/publish-it', PublishArticle),
							   webapp2.Route(r'/login/<:.*>', Login, handler_method='any'),
							   webapp2.Route(r'/logout', MainPage)],
                                debug=True)

								
''' 
create a new Secret entity in the dataStore for each provider if one does not
already exist. New providers must have their Secret entities updated manually
using the edit entity feature of the App Engine developer console
'''

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

#update CONFIG with stored secrets
for provider in CONFIG:
    try:
        CONFIG[provider]['consumer_key'] = storedProviders[provider]['consumer_key']
        CONFIG[provider]['consumer_secret'] = storedProviders[provider]['consumer_secret']
    except KeyError:
        logging.info("The secrets for new provider %s may not have been updated", provider)