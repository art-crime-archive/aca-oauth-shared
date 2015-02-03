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
#security
import gae_secrets
import hashlib

from authomatic import Authomatic
from authomatic.adapters import Webapp2Adapter
from config import CONFIG
import Cookie

from google.appengine.ext import deferred
from google.appengine.runtime import DeadlineExceededError
import update_schema

authomatic = Authomatic(config=CONFIG, secret='some random secret string')
#Authomatic Integration - Alex Anderson
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
		self.oauthid = user_provider
		if user_email:
			self.oauthid = hashlib.sha256(CONFIG['salt']['consumer_secret'] + user_email).hexdigest()
	def __str__(self):
		return self.nickname();
	def nickname(self):
		if self.name:
			return self.name
		elif self.emailaddress:
			return self.emailaddress.split('@')[0]
	def oAuthNickname(self):
		try:
			return self.nickname()+'@'+self.oauthid
		except TypeError:
			return self.nickname()+'@'+self.provider
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
		isAuthor = False
		shouldUpdate = update and article
		if article and not comments:
			#merge account match Dan's Method (no need to update)
			try:
				if article.oauthid == self.oauthid:
					return isAuthor
			#if article is missing oauthid then we need to update structure*
			except AttributeError:
				isAuthor = False
				shouldUpdate = True
			#check if providers match and if we need to update structure*
			try:
				isSameProvider = article.provider == self.provider
			except AttributeError:
				isSameProvider = False
				shouldUpdate = True
			#Alex's Method Lines up unique username and login method
			if article.author == self.nickname() and isSameProvider:
				if shouldUpdate:
					article.author = self.nickname()
					article.oauthid = self.oauthid
					article.provider = self.provider
					article.put()
				return True
			#Old GAE Account Method (need to update structur)
			elif self.emailaddress:
				if article.author == self.emailaddress or article.author == self.emailaddress.split('@')[0]: #isGmail(article.author) and
					#should we update the article author?
					if shouldUpdate:
						article.author = self.nickname()
						article.oauthid = self.oauthid
						article.provider = self.provider
						article.put()
					return True
			return False
		elif comments: #save network time by doing algorithm in bulk
			commentid = 0
			for comment in comments:
				commentObj = loads(str(comment))
				commentAuthor = str(commentObj[1])
				try:
					commentTail = str(commentObj[1]).split('@',2)[1]
				except:
					commentTail = None
				#comment's Text = commentObj[0]
				#comment's Time = commentObj[2]
				shouldUpdate = update and article
				#Format: Nickname()@oauthid Dan's Method
				if commentAuthor and commentTail == self.oauthid:
					isAuthor = True
				elif commentAuthor == self.name: #Alex's Method (BAD! Username Overlap definitely needs Update!)
					isAuthor = True
					if shouldUpdate:
						pickled = db.Text(dumps([commentObj[0], self.oAuthNickname(), commentObj[2]]))
						article.comments[commentid] = pickled
					else:
						return isAuthor
				elif self.emailaddress: #Old GAE Account Method
					if commentAuthor == self.emailaddress or commentAuthor == self.emailaddress.split('@')[0]:
						isAuthor = True
						if shouldUpdate:
							pickled = db.Text(dumps([commentObj[0], self.oAuthNickname(), commentObj[2]]))
							article.comments[commentid] = pickled
						else:
							return isAuthor
				commentid += 1
		elif comment: #do one comment
			commentObj = loads(str(comment))
			commentAuthor = str(commentObj[1])#.split('@',2)[0]
			try:
				commentTail = str(commentObj[1]).split('@',2)[1]
			except:
				commentTail = None
			#Merge match
			if commentAuthor and commentTail == self.oauthid:
				isAuthor = True
			elif commentAuthor == self.name:
				isAuthor = True
				if shouldUpdate:
					pickled = db.Text(dumps([commentObj[0], self.oAuthNickname(), commentObj[2]]))
					article.comments[commentid] = pickled
				else:
					return isAuthor
			elif self.emailaddress: #old matches
				if commentAuthor == self.emailaddress or commentAuthor == self.emailaddress.split('@')[0]:
					isAuthor = True
					if shouldUpdate:
						pickled = db.Text(dumps([commentObj[0], self.oAuthNickname(), commentObj[2]]))
						article.comments[commentid] = pickled
					else:
						return isAuthor
		if shouldUpdate:
			article.put()
		return isAuthor

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
		return cookie.output();
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

#adjusted from authomatic website example
class Login(webapp2.RequestHandler):

	# The handler must accept GET and POST http methods and
	# Accept any HTTP method and catch the "provider_name" URL variable.
	def any(self, provider_name):
		#make sure we're not already logged in! don't waste api calls!
		user = oAuthUser.fromCookie()
		redirect = getRedirect()
		self.response.delete_cookie('user_redirect')
		if user:
			if user.name and user.provider:
				self.response.delete_cookie('error')
				self.redirect(redirect)
		
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
				self.redirect(redirect)
			elif result.error:
				self.response.set_cookie('error', urllib.quote(result.error.message))
				self.response.out.write(str(result.error.message))

class Theme(webapp2.RequestHandler):
	def any(self, theme_name):
		#Make a list of directory names* Check if theme_name in list
		if theme_name:
			if theme_name == 'cleanblog':
				self.response.set_cookie('user_theme', theme_name)
			elif theme_name == 'default':
				self.response.delete_cookie('user_theme')
			else:
				self.response.delete_cookie('user_theme')
		else:
			self.response.delete_cookie('user_theme')
		self.redirect('/')
				
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

def getTheme():
	theme = None
  	cookie_string = os.environ.get('HTTP_COOKIE')
	if cookie_string:
		cookie = Cookie.SimpleCookie()
		cookie.load(cookie_string)
		try:
			theme = cookie['user_theme'].value
		except:
			theme = None
	return theme

def getRedirect():
	redirect = '/'
  	cookie_string = os.environ.get('HTTP_COOKIE')
	if cookie_string:
		cookie = Cookie.SimpleCookie()
		cookie.load(cookie_string)
		try:
			redirect = cookie['user_redirect'].value
		except:
			redirect = '/'
	return redirect
	
def TemplateObject(object, values, theme = None, select = 0):
	path = ThemeTemplate(theme)
	tree = SafeTree(template.render(path, values))
	return TreeObject(tree, object, select)

def TreeObject(tree, object, select = 0):
	treeList = tree.xpath('//*[@data-template-object="'+object+'"]')
	try:
		return tostring(treeList[select])
	except IndexError:
		return ''
	
def ThemeTemplate(theme = None, path = 'template.html'):
	if theme:
		template_file = os.path.join(os.path.dirname(__file__),'templates',theme,path)# 'static/templates/'+theme+'/'+path
	else:
		template_file = os.path.join(os.path.dirname(__file__),path)
	return os.path.join(os.path.dirname(__file__), template_file )

def SafeTree(string):
	try:
		return fragment_fromstring(string, create_parent=False)
	except: #Wraps whatever was loaded with a <div> element
		return fragment_fromstring(string, create_parent=True)
	
def format_comments(comments=None, article_id=None, theme=None, select=0):
	template_data = {
		  'user_activity': '',
		  'article_id': article_id,}
#todo - build comment tree by replacing and adding.
#todo - add report abuse.
	#path = os.path.join(os.path.dirname(__file__), 'comment-table-template.html' )
	path = ThemeTemplate(theme)
	all_comments = '<div class="below-video comments">Comments:<table>'
	template_data.update({'comment_id': len(comments)})
	tree = SafeTree(template.render(path, template_data))
	all_comments += TreeObject(tree, "comment-add") #tostring(tree.xpath('//tfoot')[0])#needs better element addressing
	#all_comments += tostring(tree.xpath('//[@data-template-comment='4']')[0])#alex better element addressing
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
		tree = SafeTree(template.render(path, template_data))
		if nickname != '':
			all_comments += TreeObject(tree, "comment")
		else:
			all_comments += TreeObject(tree, "comment-deleted")
		comment_id += 1
	
	#place an empty hidden comment last
	template_data.update({'comment_id': len(comments)})
	tree = tree = SafeTree(template.render(path, template_data))
	all_comments += TreeObject(tree, "comment-hidden")
	all_comments += '</tbody></table></div>'
	return all_comments

def format_article(article, all_articles, theme = None, select = 0):
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
			#Update comments #comment_id = 0 #for comment in article.comments:
			user.isAuthor(article=article,comments=article.comments,update=True)
		article_link = '/article?id=%s' % (article.key().id())
		article_author_link = '/by-author?author=%s&provider=%s' % (article.author.split('@',2)[0], article.provider)
		article_author = article.author.split('@',2)[0]
		article_comments = format_comments(article.comments, article.key().id(), theme, select)
		template_data = {
		  'edit_link': edit_link,
		  'view_status': view_status,
		  'article_author': article_author,
		  'article_embed': article.embed,
		  'article_link': article_link,
		  'article_content': article.content,
		  'article_tags': article.tags,
		  'article_comments': article_comments,
		  'article_author_link': article_author_link,
		  'article_title': article.title,
		  }		
		#todo - move to article template file
		#all_articles += '<div class="embed">%s</div>' % article.embed
		#all_articles += '<div class="title"> <a class="article-link no-ajax" href="/article?id=%s">%s</a> ' % (article.key().id(), article.title)
		#all_articles += '<span class="author"> by <a class="author-link no-ajax" href="/by-author?author=%s&provider=%s">%s</a> </span>' % (article.author.split('@',2)[0],article.provider, article.author.split('@',2)[0])
		#all_articles += '<span> %s %s </span></div>' % (view_status, edit_link)
		#all_articles += '<div class="below-video article"><pre>%s</pre></div>' % article.content
		#all_articles += '<div class="below-video tags">Tags: %s</div>' % article.tags
		all_articles += TemplateObject("article",template_data, theme, select) #format_comments(article.comments, article.key().id())
	return all_articles
	
def get_articles(ids=None, author=None, limit=None, bookmark=None, provider=None, view=None, user=None, theme=None, select=0):
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
		all_articles = format_article(article, all_articles, theme, select)

	if next:
		template_data = {
			'next_url': next,
		}
		all_articles += TemplateObject("pagination",template_data,theme,select)
	#else:
	#	all_articles += '<div class="bookmark-end">No more articles.</div>'
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
	theme = getTheme()
	select = 0
	style = ''
	#user = users.get_current_user()
	user = oAuthUser.fromCookie()
	if user:
		greeting = ('<div class="signed-in" nickname="%s"> %s <a class="sign-out no-ajax" href="%s">(sign out)</a></div>' % (user.nickname(), user.nickname(), oAuthUsers.create_logout_url("/")))
		nickname = user.nickname()
	else:
		greeting = ('<a id="not-signed-in" class="sign-in" href="%s">Sign in or register</a>' % (oAuthUsers.create_login_url("/")))
		nickname = ''

	content = ''
	content_id =  self.request.path[1:]

	#faster execution using elif blocks
	if not (self.request.path == '/auth' or self.request.path == 'logout'):
		self.response.set_cookie('user_redirect', self.request.path)
		
	if self.request.get('bookmark'):
		content_id += '-next'
	 
	elif self.request.path == '/':
		return self.redirect('/the-archive')
	  
	elif self.request.path == '/article':
		#select needs to be picked from a file
		try:
			content = format_article(Articles().get_by_id(int(self.request.get('id')), parent=archive_key()), '',theme,select = 1)
		except:
			return self.redirect('/the-archive')

	elif self.request.path == '/by-author':
		author = self.request.get('author')
		authorprovider = self.request.get('provider')
		content = '<div class="below-video"><span class="author"> Articles with Author Name: <a class="author-link" href="/by-author?author=%s">%s</a> </span>' % (author, author)
		for provider in CONFIG:
			object = 'login-'+provider
			login = "/by-author?author=%s&provider=%s" % (author,provider)
			matched = authorprovider == provider
			if matched:
				content += '<span>|</span>'
			template_data = {
				'login_url': login
			}
			content += TemplateObject(object, template_data, theme, select)
			if matched:
				content += '<span>|</span>'
		content += '</div>'
		content += get_articles(author = self.request.get('author'),provider = self.request.get('provider'), theme=theme,select=select)
	elif self.request.path == '/auth':
		content = ''
		for provider in CONFIG:
			object = 'login-'+provider
			login = "/login/%s" % provider
			template_data = {
				'login_url': login
			}
			content += TemplateObject(object, template_data, theme, select)
			
	elif self.request.path == '/logout':
		self.response.delete_cookie('user_id')
		self.response.delete_cookie('user_name')
		self.response.delete_cookie('user_email')
		self.response.delete_cookie('credentials')
		self.response.delete_cookie('user_provider')
		self.response.delete_cookie('error')
		redirect = getRedirect()
		#content = ''
		#for provider in CONFIG:
		#	content += '<a href="/login/%s">%s</a><br>' % (provider,provider)
		self.redirect(redirect);
	
	elif self.request.path[:12] == '/curated':
		for id in open('archive-list.txt', 'r').read().split():
			content += format_article(Articles().get_by_id(int(id), parent=archive_key()), '')
							 
	elif self.request.path[:12] == '/the-archive':
		content = get_articles(limit = self.request.get('limit'),
							bookmark = self.request.get('bookmark'),
							theme=theme,
							select=select)
							 
	elif self.request.path[:12] == '/featured':
		content = get_articles(ids = 
		[11006, 97006, 98006, 91006, 91004, 95001, 46003, 87006, 85006, 59001,
		49001, 9001, 10001, 23008, 31006, 4001, 13001, 21012, 35008, 21005,
		27001, 18002, 5001, 7001, 25001, 12002, 28011, 8002, 22002],
		theme=theme,
		select=select)

	elif self.request.path == '/test':
		content = ''
	elif self.request.path[:12] == '/my-articles':
		if user:
			content = get_articles(author = user.nickname(),
							   limit = self.request.get('limit'),
							   bookmark = self.request.get('bookmark'),
							   user = user,
							   provider = user.provider,
							   theme = theme,
							   select = select)
			if user.emailaddress: #get older database articles
				content += get_articles(author = user.emailaddress,
								   limit = self.request.get('limit'),
								   bookmark = self.request.get('bookmark'),
								   user = user,
								   provider = user.provider,
								   theme = theme,
								   select = select)			
			
		else:
			if 'X-Requested-With' in self.request.headers:
				return self.error(500)
			else:
				return self.redirect(oAuthUsers.create_login_url("/my-articles"))
		
	elif self.request.path == '/about':
		tree = html.parse('About-the-Art-Crime-Archive.html')
		style = tostring(tree.xpath('//style')[0])
		content = innerHTML('About-the-Art-Crime-Archive.html', 'body')
	else: #no url match? Well then
		content = 'Whoops! No Content For This Url!'

	javascripts = """
	<script src="http://ajax.googleapis.com/ajax/libs/jquery/1.8.2/jquery.js"></script>
    <script src="../static/js/jquery.fitvids.js"></script>
	<script src='../static/js/jquery.autosize.js'></script>
    <script src="../static/js/jquery.hint.js"></script>
	<script src='../static/js/jquery.history.js'></script>
    <script src="../static/js/bootstrap.js"></script>
	<script src="../static/js/ajaxHTML5.js"></script>
    <script src="../static/js/aca.js"></script>
	%s
	""" % ('')
	
	template_data = {
			'content_id': content_id,
			'content': content,
			'nickname': nickname,
			'greeting': greeting,
			'style': style,
			'javascripts': javascripts
			}

	path = ThemeTemplate(theme,'index.html') #os.path.join(os.path.dirname(__file__), 'index.html' )
	self.response.headers['X-XSS-Protection'] = '0' #prevents blank embed after post
	#try:
	self.response.out.write(template.render(path, template_data))
	#except: #whoops theme didn't exist
	#	path = ThemeTemplate(None,'index.html')
	#	self.response.out.write(template.render(path, template_data))

class ArticleForm(webapp2.RequestHandler):
  def get(self):
	user = oAuthUser.fromCookie() #users.get_current_user()
	if user:
		greeting = ('<div class="signed-in" nickname="%s"> %s <a class="sign-out no-ajax" href="%s">(sign out)</a></div>' % (user.nickname(), user.nickname(), oAuthUsers.create_logout_url("/")))
		nickname = user.nickname()
		template_values = {
			'greeting': greeting,
			'user': user.nickname(),
		}
		theme = getTheme()
		select = 0
		style = ''
	else:
		if 'X-Requested-With' in self.request.headers:
			return self.error(500)
		else:
			self.response.set_cookie('user_redirect', self.request.path)
			return self.redirect(oAuthUsers.create_login_url("/create-article"))
	
	content_id =  self.request.path[1:]
	content = ''
	if self.request.path == '/create-article':
		content = """
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
			  """ % content_id
	elif self.request.path == '/edit-article-form':
		article_id = int(self.request.get('id'))
		article = Articles(parent=archive_key()).get_by_id(article_id, parent=archive_key())
		if user.isAuthor(article=article,update=True) or user.isAdmin():
			content = """
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
				  """ % (content_id, article_id, article_id, article.embed, article.title, 
						 sub('<[^>]*>', '', article.content), article.tags)
	
	javascripts = """
	<script src="http://ajax.googleapis.com/ajax/libs/jquery/1.8.2/jquery.js"></script>
    <script src="../static/js/jquery.fitvids.js"></script>
	<script src='../static/js/jquery.autosize.js'></script>
    <script src="../static/js/jquery.hint.js"></script>
	<script src='../static/js/jquery.history.js'></script>
    <script src="../static/js/bootstrap.min.js"></script>
    <script src="../static/js/aca.js"></script>
	%s
	""" % ('')
	
	template_data = {
			'content_id': content_id,
			'content': content,
			'nickname': nickname,
			'greeting': greeting,
			'style': style,
			'javascripts': javascripts
			}
	
	path = ThemeTemplate(theme,'index.html') #os.path.join(os.path.dirname(__file__), 'index.html' )
	self.response.headers['X-XSS-Protection'] = '0' #prevents blank embed after post
	self.response.out.write(template.render(path, template_data))
		  
class PublishArticle(webapp2.RequestHandler):
  def post(self):
	if self.request.get('id') is not '':
		article_id = int(self.request.get('id'))
		article = Articles(parent=archive_key()).get_by_id(article_id, parent=archive_key())
	else:
		article = Articles(parent=archive_key())

	user = oAuthUsers.get_current_user()
	article.author = user.nickname()
	article.embed = self.request.get('embed-code')
	article.title = self.request.get('title')
	article.content = self.request.get('content')
	article.tags = self.request.get('tags')
	article.view = self.request.get('view')
	article.provider = user.provider
	article.oauthid = user.oauthid
	article.put()
	if article.view == 'Preview' or article.view == 'Retract':
	  return self.redirect('/my-articles')
	return self.redirect('/')

class EditArticleForm(webapp2.RequestHandler):
  def get(self):
	user = oAuthUser.fromCookie() #users.get_current_user()
	if user:
		nickname = user.nickname()
		greeting = "<span class=\"signed-in\"> %s</span>" % user.nickname()
		template_values = {
			'greeting': greeting,
			'user': user.nickname(),
		}
		theme = getTheme()
		select = 0
		style = ''
	else:
		if 'X-Requested-With' in self.request.headers:
			return self.error(500)
		else:
			return self.redirect(oAuthUsers.create_login_url("/create-article"))
	content_id =  self.request.path[1:]
	
	article_id = int(self.request.get('id'))
	article = Articles(parent=archive_key()).get_by_id(article_id, parent=archive_key())

	content = """
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
		  """ % (content_id, article_id, article_id, article.embed, article.title, 
				 sub('<[^>]*>', '', article.content), article.tags)
	
	javascripts = """
	<script src="http://ajax.googleapis.com/ajax/libs/jquery/1.8.2/jquery.js"></script>
    <script src="../static/js/jquery.fitvids.js"></script>
	<script src='../static/js/jquery.autosize.js'></script>
    <script src="../static/js/jquery.hint.js"></script>
	<script src='../static/js/jquery.history.js'></script>
    <script src="../static/js/bootstrap.min.js"></script>
    <script src="../static/js/aca.js"></script>
	%s
	""" % ('')
	
	template_data = {
			'content_id': content_id,
			'content': content,
			'nickname': nickname,
			'greeting': greeting,
			'style': style,
			'javascripts': javascripts
			}

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
							   ('/create-article', ArticleForm),
							   ('/edit-article-form', ArticleForm),
							   ('/test', MainPage),
							   ('/auth', MainPage),
							   ('/publish-it', PublishArticle),
                               ('/update/schema',UpdateHandler),
							   webapp2.Route(r'/theme/<:.*>', Theme, handler_method='any'),
							   webapp2.Route(r'/login/<:.*>', Login, handler_method='any'),
							   webapp2.Route(r'/logout', MainPage)],
                                debug=True)
						
