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
import Cookie

from google.appengine.ext import deferred
from google.appengine.runtime import DeadlineExceededError
import update_schema

authomatic = Authomatic(config=CONFIG, secret='some random secret string')

def isGmail(string):
	if string:
		if "@gmail.com" in string:
			return True
		#google auth also allows yahoo so this counts too
		elif "@yahoo.com" in string:
			return True
		return False
	else: #Prevent Twitter crash (eg no email...definitely false)
		return False
#new user model
class oAuthUser:
	def __init__(self,user_id,user_name,user_email,user_provider,user_credentials):
		self.id = user_id
		self.name = user_name
		self.emailaddress = user_email
		self.provider = user_provider
		self.credentials = user_credentials
	def __str__(self):
		return self.nickname();
	def nickname(self):
		if self.name:
			return self.name
		elif self.emailaddress:
			return self.emailaddress.split('@')[0]
	def email(self):
		return self.email
	def user_id(self):
		return self.id
	def federated_identity(self):
		return self.id + self.provider
	def federated_provider(self):
		return self.provider
	def isUser(self,user_name,user_provider):
		return ((self.name == user_name) and (self.provider == user_provider))
	def isAuthor(self,article=None,comment=None,comments=None,update=None):
		#filter out bad source
		if article and not comments:
			if article.provider != self.provider:
				return False
			#exact match scenario
			elif article.author == self.name:
				return True
			#old match scenario
			elif self.emailaddress:
				if article.author == self.emailaddress or article.author == self.emailaddress.split('@')[0]: #isGmail(article.author) and
					#should we update the article author?
					if update and self.name:
						article.author = self.name
						article.put()
					return True
		elif comments:
			commentid = 0
			isAuthor = False
			for comment in comments:
				commentObj = loads(str(comment))
				commentAuthor = str(commentObj[1]).split('@',2)[0]
				#comment's Text = commentObj[0]
				#comment's Time = commentObj[2]
				if commentAuthor == self.name:
					isAuthor = True
					if not (update and article):
						return isAuthor
				elif self.emailaddress:
					if commentAuthor == self.emailaddress or commentAuthor == self.emailaddress.split('@')[0]:
						isAuthor = True
						if update and article:
							pickled = db.Text(dumps([commentObj[0], self.name, commentObj[2]]))
							article.comments[commentid] = pickled
						else:
							return isAuthor
				commentid += 1
			if update and article:
				article.put()
		elif comment:
			commentObj = loads(str(comment))
			commentAuthor = str(commentObj[1]).split('@',2)[0]
			#comment's Text = commentObj[0]
			#comment's Time = commentObj[2]
			if commentAuthor == self.name:
				return True
			elif self.emailaddress:
				if commentAuthor == self.emailaddress or commentAuthor == self.emailaddress.split('@')[0]:
					if update and article and commentid >= 0:
						pickled = db.Text(dumps([commentObj[0], self.name, commentObj[2]]))
						article.comments[commentid] = pickled
						article.put()
					return True
		return False

	def isAdmin(self):
		qry = AdminUser.query(AdminUser.name == self.name, AdminUser.provider == self.provider)
		for adminuser in qry:
			if adminuser.name == self.name and adminuser.provider == self.provider:
				return True
		return False
	#not working?
	def toCookie(self):
		cookie = Cookie.SimpleCookie()
		cookie.load(cookie_string)
		cookie['user_id'] = self.id
		cookie['user_name'] = urllib.quote(self.name)
		cookie['user_email'] = self.emailaddress
		cookie['user_provider'] = self.provider
		cookie['credentials'] = self.credentials
	@classmethod
	def fromCookie(self):
		cookie_string = os.environ.get('HTTP_COOKIE')
		if cookie_string:
			cookie = Cookie.SimpleCookie()
			cookie.load(cookie_string)
			try:
				user_id = cookie['user_id'].value
			except:
				user_id = None
			try:
				user_name = urllib.unquote(cookie['user_name'].value)
			except:
				user_name = None
			try:
				user_email = cookie['user_email'].value
			except:
				user_email = None
			try:
				user_provider = cookie['user_provider'].value
			except:
				user_provider = None
			try:
				credentials = cookie['credentials'].value
			except:
				credentials = None
			#Make sure we have enough to confirm a valid user
			if (user_id or user_name) and user_provider:
				return self(user_id, user_name, user_email, user_provider, credentials)
			else:
				return None
		else:
			return None
	@classmethod
	def fromAuthomatic(self, user, provider):
		if user.credentials:
			sc = user.credentials.serialize()
		else:
			sc = None
		return self(user.id,user.name,user.email,provider,sc)
		
#new user service
class oAuthUsers:
	@classmethod
	def get_oAuth_user(self):
		user = oAuthUser.fromCookie()
		if user:
			return user.nickname()
		else:
			return None
	@classmethod
	def get_current_user(self):
		return oAuthUser.fromCookie()
	@classmethod
	def create_login_url(self,urlpath=None):
		return '/auth'
	@classmethod
	def create_logout_url(self,urlpath=None):
		return '/logout'

class Login(webapp2.RequestHandler):

	# The handler must accept GET and POST http methods and
	# Accept any HTTP method and catch the "provider_name" URL variable.
	def any(self, provider_name):
		#make sure we're not already logged in! don't waste api calls!
		user = oAuthUser.fromCookie()
		if user:
			if user.name and user.provider:
				self.response.delete_cookie('error')
				self.redirect('/')
		
		# It all begins with login.
		result = authomatic.login(Webapp2Adapter(self), provider_name)

		# Do not write anything to the response if there is no result!
		if result:
			if result.user:
				result.user.update()
				if result.user.name:
					# Save the user name and ID to cookies that we can use it in other handlers.
					self.response.set_cookie('user_id', result.user.id)
					self.response.set_cookie('user_name', urllib.quote(result.user.name))
					self.response.set_cookie('user_email', result.user.email)
					self.response.set_cookie('user_provider', provider_name)
					self.response.delete_cookie('error')
				elif result.user.email:
					# Use the first part of the email as the user's name
					self.response.set_cookie('user_id', result.user.id)
					self.response.set_cookie('user_name', urllib.quote(result.user.email.split('@')[0]))
					self.response.set_cookie('user_email', result.user.email)
					self.response.set_cookie('user_provider', provider_name)
					self.response.delete_cookie('error')
				else:
					self.response.set_cookie('error', 'No user name available!')
				if result.user.credentials:
					# Serialize credentials and store it as well.
					serialized_credentials = result.user.credentials.serialize()
					self.response.set_cookie('credentials', serialized_credentials)
				self.redirect('/')
			elif result.error:
				self.response.set_cookie('error', urllib.quote(result.error.message))
				self.response.out.write(str(result.error.message))
				
class Articles(db.Model):
	"""Models an individual Archive entry"""
	author = db.StringProperty()
	embed = db.TextProperty()
	title = db.StringProperty()
	content = db.TextProperty()
	tags = db.TextProperty()
	comments = db.ListProperty(db.Text)
	view = db.StringProperty() #Publish, Preview or Retract
	date = db.DateTimeProperty(auto_now_add=True)
	provider = db.StringProperty(default='gg') #Source (Facebook, Twitter...etc)

#This provides the means of changing the database when required
class UpdateHandler(webapp2.RequestHandler):
    def get(self):
		content_id =  self.request.path[1:]
		user = oAuthUser.fromCookie()
		if user:
			if user.isAdmin():
				content = 'Schema Migration successfully initiated.'
				greeting = ('<div class="signed-in" nickname="%s">Admin: %s <a class="sign-out no-ajax" href="%s">(sign out)</a></div>' % (user.nickname(), user.nickname(), oAuthUsers.create_logout_url("/")))
				deferred.defer(update_schema.UpdateSchema)
			else:
				content = 'Schema Migration requires an Admin User!'
				greeting = ('<div class="signed-in" nickname="%s"> %s <a class="sign-out no-ajax" href="%s">(sign out)</a></div>' % (user.nickname(), user.nickname(), oAuthUsers.create_logout_url("/")))
			
			nickname = user.nickname()
		else:
			content = 'Not Logged In!'
			nickname = ''
			greeting = ('<a id="not-signed-in" class="sign-in" href="%s">Admin Sign In</a>' % oAuthUsers.create_login_url("/"))
		
		template_data = {
			'content_id': content_id,
			'content': content,
			'nickname': nickname,
			'greeting': greeting,
			'style': '',
		}

		path = os.path.join(os.path.dirname(__file__), 'index.html' )
		self.response.headers['X-XSS-Protection'] = '0' #prevents blank embed after post
		self.response.out.write(template.render(path, template_data))
			
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
	user = oAuthUsers.get_current_user()
	for comment in comments:
		nickname = str(loads(str(comment))[1]).split('@',2)[0]
		dispNickname = nickname
		if user:
			#The display nickname will break the code to comment, leave as is
			#if the author actually matches up
			if user.isAuthor(comment=comment):
				dispNickname = nickname
			#Make it obvious who is the owner
			elif dispNickname != '':
				dispNickname = '['+nickname+']'
		template_data.update({
			'comment_id': str(comment_id),
			'comment_display': loads(str(comment))[0],
			'nickname': dispNickname,
			'comment_date': loads(str(comment))[2],
			'time_now': datetime.now(),
			'user_url': 'by-author?author='+urllib.quote(nickname),
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
	user = oAuthUser.fromCookie()
	#We can't add an article to a list of articles if it doesn't exist!
	if article:
		if user:	
			if user.isAuthor(article=article,update=True):	
				edit_link = '<a class="links" href="/edit-article-form?id=%s">edit</a>' % article.key().id()
				if article.view != 'Publish':
					view_status = '<a class="view-status" href="/edit-article-form?id=%s">not published</a>' % (article.key().id())
			#Update comments
			#comment_id = 0
			#for comment in article.comments:
			user.isAuthor(article=article,comments=article.comments,update=True)
			#	comment_id +=1
					
		#todo - move to article template file
		all_articles += '<div class="embed">%s</div>' % article.embed
		all_articles += '<div class="title"> <a class="article-link no-ajax" href="/article?id=%s">%s</a> ' % (article.key().id(), article.title)
		all_articles += '<span class="author"> by <a class="author-link no-ajax" href="/by-author?author=%s">%s</a> </span>' % (article.author.split('@',2)[0], article.author.split('@',2)[0])
		all_articles += '<span> %s %s </span></div>' % (view_status, edit_link)
		all_articles += '<div class="below-video article"><pre>%s</pre></div>' % article.content
		all_articles += '<div class="below-video tags">Tags: %s</div>' % article.tags
		all_articles += format_comments(article.comments, article.key().id())
	return all_articles
	
def get_articles(ids=None, author=None, limit=None, bookmark=None, provider=None, view=None, user=None):
	"""Retrieves articles from Archive entity and composes HTML."""
	if not limit:
		limit = 10

	articles = Articles().all().order("-date")
	if not user:
		articles = articles.filter('view =', 'Publish')
  
	if ids:
		limit = len(ids)
		articles = Articles().get_by_id(ids, parent=archive_key())
		all_articles =''
		for article in articles:
			all_articles = format_article(article, all_articles)
		return all_articles

	if author:
		#articles = Articles().all().order("-date").filter('author =', author)
		articles = Articles().all().order("author").filter('author >=', author).filter('author <', author + u'\ufffd')
		articles = articles.order('-date')

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

class GetPage(webapp2.RequestHandler):
	def get(self):
		page = self.request.path[1:]
		template_values = {
				'content': innerHTML(page + '.html', 'body'),
				'content_id': page,
				}

		path = os.path.join(os.path.dirname(__file__), 'index-template.html' )
		self.response.out.write(template.render(path, template_values))

class MainPage(webapp2.RequestHandler):
  def get(self):
	style = ''
	#user = users.get_current_user()
	user = oAuthUser.fromCookie()
	if user:
		greeting = ('<div class="signed-in" nickname="%s"> %s <a class="sign-out no-ajax" href="%s">(sign out)</a></div>' % (user.nickname(), user.nickname(), oAuthUsers.create_logout_url("/")))
		nickname = user.nickname()
	else:
		greeting = ('<a id="not-signed-in" class="sign-in" href="%s">Sign in or register</a>' % oAuthUsers.create_login_url("/"))
		nickname = ''
	#user = oAuthUser.fromCookie()
	#Pull user data from cookies
	#error = urllib.unquote(self.request.cookies.get('error', ''))
	#if error:
	#	user_id = None
	#	nickname = ''
	#elif user:
	#	self.response.delete_cookie('error')
	#	error = None
	#	nickname = user.nickname()
	#	user_id = user.id
	#	user_provider = user.provider
	#else:
	#	nickname = ''
	#	user_id = None

	#if error:
	#	greeting = '%s: <a id="not-signed-in" class="sign-in" href="/auth">Login</a>' % (error)
	#	nickname = ''	  
	#elif user_id:
	#	greeting = ('<div class="signed-in" nickname="%s"> %s <a class="sign-out no-ajax" href="%s">(sign out)</a></div>' % (nickname, nickname, "/logout"))
	#else:
	#	greeting = 'Sign in with: <a id="not-signed-in" class="sign-in" href="/auth">Login</a>'
	#	nickname = ''
	#self.response.delete_cookie('error')

	content = 'No content for this URL'
	content_id =  self.request.path[1:]

	#faster execution using elif blocks
	if self.request.get('bookmark'):
		content_id += '-next'
	 
	elif self.request.path == '/':
		return self.redirect('/the-archive')
	  
	elif self.request.path == '/article':
		content = format_article(Articles().get_by_id(int(self.request.get('id')), parent=archive_key()), '')

	elif self.request.path == '/by-author':
		content = '<div class="below-video"><span class="author"> All articles by <a class="author-link no-ajax" href="/by-author?author=%s">%s</a> </span></div>' % (self.request.get('author'), self.request.get('author'))
		content += get_articles(author = self.request.get('author'))
	elif self.request.path == '/auth':
		content = ''
		for provider in CONFIG:
			content += '<a class="sign-in" href="/login/%s">%s</a><br>' % (provider,provider)
			
	elif self.request.path == '/logout':
		self.response.delete_cookie('user_id')
		self.response.delete_cookie('user_name')
		self.response.delete_cookie('user_email')
		self.response.delete_cookie('credentials')
		self.response.delete_cookie('user_provider')
		self.response.delete_cookie('error')
		
		#content = ''
		#for provider in CONFIG:
		#	content += '<a href="/login/%s">%s</a><br>' % (provider,provider)
		self.redirect('/auth');
	
	elif self.request.path[:12] == '/curated':
		for id in open('archive-list.txt', 'r').read().split():
			content += format_article(Articles().get_by_id(int(id), parent=archive_key()), '')
							 
	elif self.request.path[:12] == '/the-archive':
		content = get_articles(limit = self.request.get('limit'),
							bookmark = self.request.get('bookmark'))
							 
	elif self.request.path[:12] == '/featured':
		content = get_articles(ids = 
		[11006, 97006, 98006, 91006, 91004, 95001, 46003, 87006, 85006, 59001,
		49001, 9001, 10001, 23008, 31006, 4001, 13001, 21012, 35008, 21005,
		27001, 18002, 5001, 7001, 25001, 12002, 28011, 8002, 22002])

	elif self.request.path == '/test':
		content = ''
	elif self.request.path[:12] == '/my-articles':
		if user:
			content = get_articles(author = user.nickname(),
							   limit = self.request.get('limit'),
							   bookmark = self.request.get('bookmark'),
							   user = user,
							   provider = user.provider)
			if user.emailaddress: #get older database articles
				content += get_articles(author = user.emailaddress,
								   limit = self.request.get('limit'),
								   bookmark = self.request.get('bookmark'),
								   user = user,
								   provider = user.provider)			
			
		else:
			if 'X-Requested-With' in self.request.headers:
				return self.error(500)
			else:
				return self.redirect(oAuthUsers.create_login_url("/my-articles"))
		
	elif self.request.path == '/about':
		tree = html.parse('About-the-Art-Crime-Archive.html')
		style = tostring(tree.xpath('//style')[0])
		content = innerHTML('About-the-Art-Crime-Archive.html', 'body')
  
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
	user = oAuthUser.fromCookie() #users.get_current_user()
	if user:
		greeting = "<span class=\"signed-in\"> %s</span>" % user.nickname()
		template_values = {
			'greeting': greeting,
			'user': user.nickname(),
		}
	else:
		if 'X-Requested-With' in self.request.headers:
			return self.error(500)
		else:
			return self.redirect(oAuthUsers.create_login_url("/create-article"))
	  
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
	if self.request.get('id') is not '':
		article_id = int(self.request.get('id'))
		article = Articles(parent=archive_key()).get_by_id(article_id, parent=archive_key())
	else:
		article = Articles(parent=archive_key())

	article.author = oAuthUsers.get_current_user().nickname()
	article.embed = self.request.get('embed-code')
	article.title = self.request.get('title')
	article.content = self.request.get('content')
	article.tags = self.request.get('tags')
	article.view = self.request.get('view')
	article.provider = oAuthUsers.get_current_user().provider
	article.put()
	if article.view == 'Preview' or article.view == 'Retract':
	  return self.redirect('/my-articles')
	return self.redirect('/')

class EditArticleForm(webapp2.RequestHandler):
  def get(self):
	article_id = int(self.request.get('id'))
	article = Articles(parent=archive_key()).get_by_id(article_id, parent=archive_key())
	
	user = oAuthUsers.get_current_user()
	if not user:
	  return self.redirect(oAuthUsers.create_login_url("/"))

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
							   ('/curated', MainPage), 
							   ('/by-author', MainPage), 
							   ('/featured', MainPage), 
							   ('/featured-next', MainPage), 
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
                               ('/update-schema',UpdateHandler),
							   webapp2.Route(r'/login/<:.*>', Login, handler_method='any'),
							   webapp2.Route(r'/logout', MainPage)],
                                debug=True)

#Create an admin user for every form of login*
class AdminUser(ndb.Model):
	provider = ndb.StringProperty()
	name = ndb.StringProperty()

def newAdminUser(provider):
	return AdminUser(parent=akey, provider=provider, name='admin')

akey = ndb.Key('AdminUser', 'admin_users')
admin_query = AdminUser.query(ancestor=akey)
admins = admin_query.fetch()
storedAdmins = {a.provider: {'name':a.name} for a in admins}

ndb.put_multi(newAdminUser(p) for p in CONFIG if p not in storedAdmins)
								
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