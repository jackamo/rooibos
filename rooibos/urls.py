from django.conf.urls.defaults import *

# Uncomment the next two lines to enable the admin:
from django.contrib import admin
admin.autodiscover()

urlpatterns = patterns('',
    # Uncomment the next line to enable admin documentation:
    # (r'^admin/doc/', include('django.contrib.admindocs.urls')),

    # Uncomment the next line for to enable the admin:
    (r'^admin/(.*)', admin.site.root),
    
    (r'^explore/', include('rooibos.solr.urls')),
    (r'^media/', include('rooibos.storage.urls')),
    (r'^data/', include('rooibos.data.urls')),
    (r'^legacy/', include('rooibos.legacy.urls')),
    (r'^nasa/', include('rooibos.nasa.urls')),
)
