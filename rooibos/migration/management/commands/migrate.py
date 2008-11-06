from django.core.management.base import BaseCommand
from django.template.defaultfilters import slugify
from xml.dom import minidom
import os
import pyodbc
from datetime import datetime
from rooibos.data.models import Group, Field, FieldValue, Record
from rooibos.storage.models import Storage, Media
from rooibos.solr.models import DisableSolrUpdates, SolrIndex
from django.db import connection

IMPORT_COLLECTIONS = (15,)
IMPORT_RECORDS = 1000

class Command(BaseCommand):
    help = 'Migrates database from older version'
    args = "config_file"

    def readConfig(self, file):
        connection = None
        servertype = None        
        config = minidom.parse(file)
        for e in config.getElementsByTagName('database')[0].childNodes:
            if e.localName == 'connection':
                connection = e.firstChild.nodeValue
            elif e.localName == 'servertype':
                servertype = e.firstChild.nodeValue
        return (servertype, connection)

    def clearDatabase(self):
        SolrIndex().clear()
        cursor = connection.cursor()
        cursor.execute("DELETE FROM storage_media")        
        cursor.execute("DELETE FROM storage_storage")
        cursor.execute("DELETE FROM data_fieldvalue")
        cursor.execute("DELETE FROM data_field")
        cursor.execute("DELETE FROM data_group_records")
        cursor.execute("DELETE FROM data_record")
        cursor.execute("DELETE FROM access_accesscontrol")
        cursor.execute("DELETE FROM data_group_subgroups")
        cursor.execute("DELETE FROM data_group")
        

    def handle(self, *config_files, **options):
        if len(config_files) != 1:
            print "Please specify exactly one configuration file."
            return
        
        servertype, connection = self.readConfig(config_files[0])
        
        conn = None
        if servertype == "MSSQL":
            conn = pyodbc.connect('DRIVER={SQL Server};%s' % connection)
        elif servertype == "MYSQL":
            conn = pyodbc.connect('DRIVER={MySQL};%s' % connection)
        else:
            print "Unsupported database type"
            return
        
        cursor = conn.cursor()
        row = cursor.execute("SELECT Version FROM DatabaseVersion").fetchone()
        version = row.Version
        
        if version != "00008":
            print "Database version is not supported"
            return
        
        print "Migrating from version %s" % version

        DisableSolrUpdates()        
        self.clearDatabase()        
        
        # Migrate collections and collection groups
         
        print "Migrating collections"
        groups = {}
        collgroups = {}
        storage = {}

        for row in cursor.execute("SELECT ID,Title FROM CollectionGroups"):
            collgroups[row.ID] = Group.objects.create(title=row.Title)

        for row in cursor.execute("SELECT ID,Type,Title,Description,UsageAgreement,GroupID,ResourcePath FROM Collections"):
            if row.ID in IMPORT_COLLECTIONS:
                manager = None
                if row.Type == 'N':
                    manager = 'nasaimageexchange'
                groups[row.ID] = Group.objects.create(title=row.Title, description=row.Description, agreement=row.UsageAgreement)            
                if collgroups.has_key(row.GroupID):
                    collgroups[row.GroupID].subgroups.add(groups[row.ID])
                if row.Type in ('I', 'N', 'R'):
                    storage[row.ID] = Storage.objects.create(title=row.Title, system='local', base=row.ResourcePath.replace('\\', '/'))

        # Migrate fields
        
        print "Migrating fields"
        fields = {}
        
        for row in cursor.execute("SELECT ID,Name FROM FieldDefinitions"):
            fields[row.ID] = Field.objects.create(label=row.Name)
     
        # Migrate records and media
        
        print "Migrating records"
        images = {}
        count = 0
        
        for row in cursor.execute("SELECT ID,CollectionID,Resource,Created,Modified,RemoteID," +
                                  "CachedUntil,Expires,UserID,Flags FROM Images"):
            if groups.has_key(row.CollectionID):
                images[row.ID] = Record.objects.create(created=row.Created or row.Modified or datetime.now(),
                                                       name=row.Resource.rsplit('.', 1)[0],
                                                       modified=row.Modified or datetime.now(),
                                                       source=row.RemoteID,
                                                       next_update=row.CachedUntil or row.Expires)
                groups[row.CollectionID].records.add(images[row.ID])
                if storage.has_key(row.CollectionID):
                    for type in ('full', 'medium', 'thumb'):
                        Media.objects.create(
                            record=images[row.ID],
                            name=type,
                            url='%s/%s' % (type, row.Resource),
                            storage=storage[row.CollectionID],
                            mimetype='image/jpeg')          
                count += 1
                if count % 100 == 0:
                    print "%s\r" % count,
                if count >= IMPORT_RECORDS:
                    break

        # Migrate field values
        
        print "Migrating field values"
        count = 0
        
        for row in cursor.execute("SELECT ImageID,FieldID,FieldValue,OriginalValue,Type,Label " +
                                  "FROM FieldData INNER JOIN FieldDefinitions ON FieldID=FieldDefinitions.ID"):
            if images.has_key(row.ImageID):
                FieldValue.objects.create(record=images[row.ImageID],
                                          field=fields[row.FieldID],
                                          label=row.Label,
                                          value=row.FieldValue,
                                          type=row.Type == 2 and 'D' or 'T')
            count += 1
            if count % 100 == 0:
                print "%s\r" % count,
        
        # Migrate slideshows
        
        print "Migrating slideshows and slides"
        count = 0
        slideshows = {}
        for row in cursor.execute("SELECT ID,Title,Description FROM Slideshows"):
            slideshows[row.ID] = Group.objects.create(title=row.Title,description=row.Description)
        for row in cursor.execute("SELECT SlideshowID,ImageID FROM Slides"):
            if images.has_key(row.ImageID):
                slideshows[row.SlideshowID].records.add(images[row.ImageID])           
            count += 1
            if count % 100 == 0:
                print "%s\r" % count,
