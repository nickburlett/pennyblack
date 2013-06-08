from django.conf.urls.defaults import *

urlpatterns = patterns('',
    url(r'^link/(?P<mail_hash>[^/]+)/(?P<link_hash>[a-z0-9]+)/$', 'pennyblack.views.redirect_link', name='pennyblack.redirect_link'),
    url(r'^proxy/(?P<mail_hash>[^/]+)/(?P<link_hash>[a-z0-9]+)/$', 'pennyblack.views.proxy', name='pennyblack.proxy'),
    url(r'^view/mail/(?P<mail_hash>\w+)', 'pennyblack.views.view', name='pennyblack.view'),
    url(r'^view/(?P<job_slug>[\w-]+)/', 'pennyblack.views.view_public', name='pennyblack.view_public'),
    url(r'^ping/(?P<mail_hash>\w*)/(?P<filename>.*)$', 'pennyblack.views.ping', name='pennyblack.ping'),
)
