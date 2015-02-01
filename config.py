from authomatic.providers import oauth2, oauth1, openid, gaeopenid
import authomatic

#Configuration options for authomatic
CONFIG = {
    'tw': { # Your internal provider name
           
        # Provider class
        'class_': oauth1.Twitter,
        
        # Twitter is an AuthorizationProvider so we need to set several other properties too:
        'consumer_key': '########################',
        'consumer_secret': '########################',
        'id': authomatic.provider_id()
    },
    'fb': {
           
        'class_': oauth2.Facebook,
        
        # Facebook is an AuthorizationProvider too.
        'consumer_key': '########################',
        'consumer_secret': '########################',
        'id': authomatic.provider_id(),
        
        # But it is also an OAuth 2.0 provider and it needs scope.
        'scope': ['user_about_me', 'email'], 
		# 'publish_stream', 'read_stream'
    },
    'gg': {
        'class_': oauth2.Google,
        'consumer_key': '########################',
        'consumer_secret': '########################',
        'id': authomatic.provider_id(),
        'scope': ['profile','email'],
	}
}