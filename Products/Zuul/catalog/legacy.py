##############################################################################
#
# Copyright (C) Zenoss, Inc. 2017, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

from OFS.SimpleItem import SimpleItem

from Products.AdvancedQuery import And, Or, Not
from Products.Zuul.catalog.interfaces import IModelCatalogTool

#------------------------------------------------------
#                  Value Converters
#------------------------------------------------------

default_value_converter = lambda value: value

last_part_of_path_value_converter = lambda value: value.split("/")[-1]

def strip_zport_dmd_value_converter(value):
    if value.startswith("/zport/dmd"):
        return value[10:]
    return value

def add_zport_dmd_value_converter(value):
    if not value.startswith("/zport/dmd"):
        return "{}{}".format("/zport/dmd", value)
    return value

#------------------------------------------------------

class TranslationValueConverter(object):
    """ """
    def __init__(self, search=None, result=None):
        self.search_converter = default_value_converter
        self.result_converter = default_value_converter
        if search is not None:
            self.search_converter = search
        if result is not None:
            self.result_converter = result


DEFAULT_CONVERTER = TranslationValueConverter()


class LegacyFieldTranslation(object):
    def __init__(self, old, new, value_converter=None):
        self.old = old
        self.new = new
        self.value_converter = DEFAULT_CONVERTER
        if value_converter is not None:
            self.value_converter = value_converter


#------------------------------------------------------
#           Translations for legacy  catalogs
#------------------------------------------------------


GLOBAL_CATALOG_TRANSLATIONS =[
    LegacyFieldTranslation(old="uid", new="uid",
                           value_converter=TranslationValueConverter(
                                            search=add_zport_dmd_value_converter,
                                            result=strip_zport_dmd_value_converter)),
    LegacyFieldTranslation(old="id", new="id"),
    LegacyFieldTranslation(old="name", new="name"),
    LegacyFieldTranslation(old="meta_type", new="meta_type"),
    LegacyFieldTranslation(old="objectImplements", new="objectImplements"),
    LegacyFieldTranslation(old="path", new="path"),
    LegacyFieldTranslation(old="searchIcon", new="searchIcon"),
    LegacyFieldTranslation(old="searchKeywords", new="searchKeywords"),
    LegacyFieldTranslation(old="searchExcerpt", new="searchExcerpt"),
    LegacyFieldTranslation(old="allowedRolesAndUsers", new="allowedRolesAndUsers"),
    LegacyFieldTranslation(old="monitored", new="monitored"),
    LegacyFieldTranslation(old="macAddresses", new="macAddresses"),
    LegacyFieldTranslation(old="ipAddress", new="text_ipAddress"),
    LegacyFieldTranslation(old="uuid", new="uuid"),
    # LegacyFieldTranslation(old="productKeys", new="productKeys"), we currently dont have it
    LegacyFieldTranslation(old="zProperties", new="zProperties"),
    LegacyFieldTranslation(old="collectors", new="collectors"),
]


DEVICE_CATALOG_TRANSLATIONS = [
    LegacyFieldTranslation(old="getDeviceIp", new="text_ipAddress"),
    LegacyFieldTranslation(old="getPhysicalPath", new="uid"),
    LegacyFieldTranslation(old="titleOrId", new="name"),
    LegacyFieldTranslation(old="id", new="id"),
    LegacyFieldTranslation(old="getPrimaryId", new="uid"),
    LegacyFieldTranslation(old="path", new="path",
                           value_converter=TranslationValueConverter(
                                result=lambda x: [ tuple(p.split("/")) for p in x ])),
    # These fields need to be added
    # LegacyFieldTranslation(old="getDeviceClassPath", new="YYYYY"),
    # LegacyFieldTranslation(old="getAdminUserIds", new="YYYYYY"),
]


LAYER_2_CATALOG_TRANSLATIONS = [
    LegacyFieldTranslation(old="macaddress", new="macaddress"),
    LegacyFieldTranslation(old="interfaceId", new="interfaceId"),
    LegacyFieldTranslation(old="deviceId", new="deviceId"),
    LegacyFieldTranslation(old="lanId", new="lanId"),
]


LAYER_3_CATALOG_TRANSLATIONS = [
    LegacyFieldTranslation(old="networkId", new="networkId"),
    LegacyFieldTranslation(old="interfaceId", new="interfaceId",
                           value_converter=TranslationValueConverter(
                                result=last_part_of_path_value_converter)),
    LegacyFieldTranslation(old="ipAddressId", new="ipAddressId"),
    LegacyFieldTranslation(old="deviceId", new="deviceId",
                           value_converter=TranslationValueConverter(
                                result=last_part_of_path_value_converter)),
]


IP_SEARCH_CATALOG_TRANSLATIONS = [
    LegacyFieldTranslation(old="path", new="uid"),
    LegacyFieldTranslation(old="ipAddressAsInt", new="decimal_ipAddress",
                           value_converter=TranslationValueConverter(result=str)),
    LegacyFieldTranslation(old="id", new="id"),
]


TRANSLATIONS = {
    "global_catalog" : GLOBAL_CATALOG_TRANSLATIONS,
    "deviceSearch"   : DEVICE_CATALOG_TRANSLATIONS,
    "layer2_catalog" : LAYER_2_CATALOG_TRANSLATIONS,
    "layer3_catalog" : LAYER_3_CATALOG_TRANSLATIONS,
    "ipSearch"       : IP_SEARCH_CATALOG_TRANSLATIONS,
}


#------------------------------------------------------


class LegacyFieldsTranslator(object):
    def __init__(self):
        self.old_fields = {}
        self.new_fields = {}

    def add_translations(self, translations):
        """
        @param translations iterable of LegacyFieldTranslation
        """
        for translation in translations:
            self.add_field_translation(translation)

    def add_field_translation(self, field_translation):
        self.old_fields[field_translation.old] = field_translation
        self.new_fields[field_translation.new] = field_translation

    def translate(self, old=None, new=None):
        translation = None
        if old:
            translation = old # We dont have a translation
            if self.old_fields.get(old):
                translation = self.old_fields[old].new
        if new:
            translation = new # We dont have a translation
            if self.new_fields.get(new):
                translation = self.new_fields[new].old
        return translation

    def convert_result_value(self, old, value):
        if value and old in self.old_fields:
            converter = self.old_fields[old].value_converter.result_converter
            value = converter(value)
        return value

    def need_search_conversion(self, old):
        needed = False
        if self.old_fields.get(old):
            converter = self.old_fields[old].value_converter
            needed = converter.search_converter != default_value_converter
        return needed

    def convert_search_value(self, old, value):
        if value and old in self.old_fields:
            converter = self.old_fields[old].value_converter.search_converter
            value = converter(value)
        return value

    def get_old_field_names(self):
        return self.old_fields.keys()

    def get_new_field_names(self):
        return self.new_fields.keys()


class LegacyCatalogAdapter(SimpleItem):
    """
    Adapt the ZCatalog interface to use model catalog for searching.
    For every search it:
        - parses the query to replace the legacy catalog indexes (fields names)
          with model catalog field names
        - sends the request to model catalog
        - converts the brains received from model catalog adding legacy catalog
          field, updating the value if needed
    """
    def __init__(self, context, zcatalog_name=None):
        """
        @param context: context to instanciate IModelCatalogTool
        @param zcatalog_name: string representing the legacyCatalog we are adapting
        """
        self.context = context
        self.zcatalog_name = zcatalog_name
        self.translator = LegacyFieldsTranslator()
        if TRANSLATIONS.get(zcatalog_name):
            translations = TRANSLATIONS.get(zcatalog_name)
            self.translator.add_translations(translations)

    def _get_model_catalog(self):
        model_catalog = IModelCatalogTool(self.context)
        if self.zcatalog_name == "deviceSearch":
            model_catalog = model_catalog.devices
        elif self.zcatalog_name == "layer2_catalog":
            model_catalog = model_catalog.layer2
        elif self.zcatalog_name == "layer3_catalog":
            model_catalog = model_catalog.layer3
        elif self.zcatalog_name == "ipSearch":
            model_catalog = model_catalog.ips
        return model_catalog

    def __call__(self, query=None, **kw):
        return self.search(query, **kw)

    def searchResults(self, query=None, **kw):
        return self.search(query, **kw)

    def evalAdvancedQuery(self, query, **kw):
        # evalAdvancedQuery(query, sortSpecs=(), withSortValues=_notPassed)
        # @TODO try to do something with the sorting....
        return self.search(query)

    def _adapt_query(self, query):
        """
        modifies a query for a legacy catalog into a model catalog query
        @param query AdvancedQuery for the legacy catalog
        """
        # we need to translate the legacy catalog fields to model catalog fields
        if isinstance(query, And) or isinstance(query, Or):
            for q in query._subqueries:
                self._adapt_query(q)
        elif isinstance(query, Not):
            self._adapt_query(query._query)
        else:
            old_field_name = query._idx
            query._idx = self.translator.translate(old=old_field_name)
            if self.translator.need_search_conversion(old_field_name):
                # dammit, we need to transform the values to search. so far only
                # uid in global catalog needs this
                if isinstance(query._term, basestring):
                    query._term = self.translator.convert_search_value(old_field_name, query._term)
                elif isinstance(query._term, tuple) or (query._term, list):
                    new_values = []
                    for value in query._term:
                        new_values.append(self.translator.convert_search_value(old_field_name, value))
                    if isinstance(query._term, tuple):
                        new_values = tuple(new_values)
                    query._term = new_values
                else:
                    pass # Not likely since only uid uses a search converter (for now....)

    def _adapt_brains(self, search_results):
        """
        @param search_results model catalog search results
        @return 
        """
        converted_brains = []
        for brain in search_results:
            # add the legacy catalog fields to the brain
            for old_field_name in self.translator.get_old_field_names():
                new_field_name = self.translator.translate(old=old_field_name)
                value = getattr(brain, new_field_name)
                value = self.translator.convert_result_value(old_field_name, value)
                setattr(brain, old_field_name, value)
            converted_brains.append(brain)
        return converted_brains

    def search(self, query, sort_index=None, reverse=False, limit=None, **kw):
        model_catalog = self._get_model_catalog()
        search_kw = {}
        if query:
            self._adapt_query(query)
        if sort_index:
            search_kw["orderby"] = sort_index
        search_kw["reverse"] = reverse
        search_kw["limit"] = limit
        search_kw["fields"] = self.translator.get_new_field_names()
        search_results = model_catalog.search(query=query, **search_kw)
        legacy_brains = self._adapt_brains(search_results)
        return legacy_brains


"""
from Products.AdvancedQuery import Eq, And, Or, Not, MatchGlob, In
from Products.Zuul.catalog.legacy import LegacyCatalogAdapter

deviceSearch = LegacyCatalogAdapter(dmd, "deviceSearch")
global_catalog = LegacyCatalogAdapter(dmd, "global_catalog")

def print_brains(brains):
    for b in brains:
           print b.getDeviceIp
           print b.getPhysicalPath
           print b.path
           print b.titleOrId
           print b.id
           print b.getPrimaryId
           print "---"


deviceSearch()
deviceSearch(Eq("titleOrId", "cisco2960G-50-5"))
deviceSearch(MatchGlob("titleOrId", "*cisco*"))
deviceSearch(In("titleOrId", ["cisco2960G-50-4", "cisco2960G-50-5"]))



global_catalog(Eq("uid", "/Devices/Network/Cisco/10-160-50-x/devices/cisco2960G-50-5"))

print_brains(deviceSearch())
print_brains(deviceSearch(Eq("titleOrId", "cisco2960G-50-5")))
print_brains(deviceSearch(MatchGlob("titleOrId", "*cisco*")))
print_brains(deviceSearch(In("titleOrId", ["cisco2960G-50-4", "cisco2960G-50-5"])))

searches = [ ]
searches.append(deviceSearch())
searches.append(deviceSearch(Eq("titleOrId", "cisco2960G-50-5")))
searches.append(deviceSearch(MatchGlob("titleOrId", "*cisco*")))

for s in searches:
    print_brains(s)
    print "\n\n"
"""


