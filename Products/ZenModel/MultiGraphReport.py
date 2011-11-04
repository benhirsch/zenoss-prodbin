###########################################################################
#
# This program is part of Zenoss Core, an open source monitoring platform.
# Copyright (C) 2007, Zenoss Inc.
#
# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License version 2 or (at your
# option) any later version as published by the Free Software Foundation.
#
# For complete information please visit: http://www.zenoss.com/oss/
#
###########################################################################

import sys
from Globals import InitializeClass
from AccessControl import ClassSecurityInfo
from Products.ZenMessaging.audit import audit
from Products.ZenUtils.deprecated import deprecated
from ZenModelRM import ZenModelRM
from Products.ZenRelations.RelSchema import *
from Products.ZenUtils.Utils import resequence, getDisplayType
from ZenossSecurity import ZEN_MANAGE_DMD
from Products.ZenWidgets import messaging

@deprecated
def manage_addMultiGraphReport(context, id, REQUEST = None):
    """ Create a new MultiGraphReport
    """
    gr = MultiGraphReport(id)
    context._setObject(gr.id, gr)
    if REQUEST is not None:
        audit('UI.Report.Add', gr.id, reportType=getDisplayType(gr), organizer=context)
        REQUEST['RESPONSE'].redirect(context.absolute_url()+'/manage_main')


class MultiGraphReport(ZenModelRM):

    meta_type = "MultiGraphReport"

    numColumns = 1
    numColumnsOptions = (1, 2, 3)

    _properties = ZenModelRM._properties + (
        {'id':'numColumns', 'type':'int', 
            'select_variable' : 'numColumnOptions', 'mode':'w'},
    )

    _relations =  (
        ('collections', 
            ToManyCont(ToOne, 'Products.ZenModel.Collection', 'report')),
        ("graphGroups", 
            ToManyCont(ToOne,"Products.ZenModel.GraphGroup", "report")),
        ('graphDefs', 
            ToManyCont(ToOne, 'Products.ZenModel.GraphDefinition', 'report')),
        )

    factory_type_information = ( 
        { 
            'immediate_view' : '',
            'actions'        :
            ( 
                {'name'          : 'View Report',
                'action'        : '',
                'permissions'   : ("View",),
                },
                {'name'          : 'Edit Report',
                'action'        : 'editMultiGraphReport',
                'permissions'   : ("Manage DMD",),
                },
            )
         },
        )

    security = ClassSecurityInfo()

    def getBreadCrumbUrlPath(self):
        """
        Return the url to be used in breadcrumbs for this object.
        """
        return self.getPrimaryUrlPath() + '/editMultiGraphReport'


    ### Graph Groups
    
    security.declareProtected('Manage DMD', 'manage_addGraphGroup')
    def manage_addGraphGroup(self, new_id, collectionId='', graphDefId='',
                                                                REQUEST=None):
        """ Add a new graph group
        """
        from GraphGroup import GraphGroup
        gg = GraphGroup(new_id, collectionId, graphDefId, 
                                            len(self.graphGroups()))
        self.graphGroups._setObject(gg.id, gg)
        gg = self.graphGroups._getOb(gg.id)
        if REQUEST:
            audit('UI.Report.AddGraphGroup', self.id, graphGroup=gg.id)
            return REQUEST['RESPONSE'].redirect(
                '%s/graphGroups/%s' % (self.getPrimaryUrlPath(), gg.id))
        return gg


    security.declareProtected('Manage DMD', 'manage_deleteGraphGroups')
    def manage_deleteGraphGroups(self, ids=(), REQUEST=None):
        """ Delete graph groups from this report
        """
        for id in ids:
            self.graphGroups._delObject(id)
        self.manage_resequenceGraphGroups()
        if REQUEST:
            for id in ids:
                audit('UI.Report.DeleteGraphGroup', self.id, graphGroup=id)
            messaging.IMessageSender(self).sendToBrowser(
                'Groups Deleted',
                'Group%s deleted: %s' % (len(ids) > 1 and 's' or '',
                                         ', '.join(ids))
            )
            return self.callZenScreen(REQUEST)


    security.declareProtected('Manage DMD', 'manage_resequenceGraphGroups')
    def manage_resequenceGraphGroups(self, seqmap=(), origseq=(), REQUEST=None):
        """Reorder the sequence of the groups.
        """
        retval = resequence(self, self.graphGroups(), seqmap, origseq, REQUEST)
        if REQUEST:
            audit('UI.Report.ResequenceGraphGroups', self.id, sequence=seqmap, oldData_={'sequence':origseq})
        return retval


    def getGraphGroups(self):
        """get the ordered groups
        """
        def cmpGroups(a, b):
            return cmp(a.sequence, b.sequence)
        groups = [g for g in self.graphGroups()]
        groups.sort(cmpGroups)
        return groups

    ### Collections

    security.declareProtected('Manage DMD', 'getCollections')
    def getCollections(self):
        """ Return an alpha ordered list of available collections
        """
        def cmpCollections(a, b):
            return cmp(a.id, b.id)
        collections = self.collections()[:]
        collections.sort(cmpCollections)
        return collections
        

    security.declareProtected('Manage DMD', 'manage_addCollection')
    def manage_addCollection(self, new_id, REQUEST=None):
        """Add a collection
        """
        from Collection import Collection
        col = Collection(new_id)
        self.collections._setObject(col.id, col)
        col = self.collections._getOb(col.id)
        if REQUEST:
            audit('UI.Report.AddCollection', self.id, collection=col.id)
            url = '%s/collections/%s' % (self.getPrimaryUrlPath(), new_id)
            return REQUEST['RESPONSE'].redirect(url)
        return col

    security.declareProtected('Manage DMD', 'manage_deleteCollections')
    def manage_deleteCollections(self, ids=(), REQUEST=None):
        """ Delete collections from this report
        """
        for id in ids:
            self.collections._delObject(id)
        if REQUEST:
            for id in ids:
                audit('UI.Report.DeleteCollection', self.id, collection=id)
            messaging.IMessageSender(self).sendToBrowser(
                'Collections Deleted',
                'Collection%s deleted: %s' % (len(ids) > 1 and 's' or '',
                                         ', '.join(ids))
            )
            return self.callZenScreen(REQUEST)


    ### Graph Definitions
         
    security.declareProtected(ZEN_MANAGE_DMD, 'getGraphDefs')
    def getGraphDefs(self):
        """ Return an ordered list of the graph definitions
        """
        def cmpGraphDefs(a, b):
            try: a = int(a.sequence)
            except ValueError: a = sys.maxint
            try: b = int(b.sequence)
            except ValueError: b = sys.maxint
            return cmp(a, b)
        graphDefs =  self.graphDefs()[:]
        graphDefs.sort(cmpGraphDefs)
        return graphDefs


    def getGraphDef(self, graphDefId):
        """ Retrieve the given graph def
        """
        rc = getattr(self.dmd.Reports, 'Multi-Graph Reports', None)
        if rc:
            return getattr(rc.graphDefs, graphDefId, None)
        return None


    security.declareProtected('Manage DMD', 'manage_addGraphDefinition')
    def manage_addGraphDefinition(self, new_id, REQUEST=None):
        """Add a GraphDefinition 
        """
        from GraphDefinition import GraphDefinition
        graph = GraphDefinition(new_id)
        graph.sequence = len(self.graphDefs())
        self.graphDefs._setObject(graph.id, graph)
        graph = self.graphDefs._getOb(graph.id)
        if REQUEST:
            audit('UI.Report.AddGraphDefinition', self.id, graphDefinition=graph.id)
            url = '%s/graphDefs/%s' % (self.getPrimaryUrlPath(), graph.id)
            return REQUEST['RESPONSE'].redirect(url)
        return graph
        

    security.declareProtected('Manage DMD', 'manage_deleteGraphDefinitions')
    def manage_deleteGraphDefinitions(self, ids=(), REQUEST=None):
        """Remove GraphDefinitions 
        """
        for id in ids:
            self.graphDefs._delObject(id)
            self.manage_resequenceGraphDefs()
        if REQUEST:
            for id in ids:
                audit('UI.Report.DeleteGraphDefinition', self.id, graphDefinition=id)
            messaging.IMessageSender(self).sendToBrowser(
                'Graphs Deleted',
                'Graph%s deleted: %s' % (len(ids) > 1 and 's' or '',
                                         ', '.join(ids))
            )
            return self.callZenScreen(REQUEST)


    security.declareProtected('Manage DMD', 'manage_resequenceGraphDefs')
    def manage_resequenceGraphDefs(self, seqmap=(), origseq=(), REQUEST=None):
        """ Reorder the sequence of the GraphDefinitions.
        """
        from Products.ZenUtils.Utils import resequence
        retval = resequence(self, self.getGraphDefs(), seqmap, origseq, REQUEST)
        if REQUEST:
            audit('UI.Report.ResequenceGraphDefinitions', self.id, sequence=seqmap, oldData_={'sequence':origseq})
        return retval

    ### Graphing
    

    def getDefaultGraphDefs(self, drange=None):
        """ Construct the list of graph dicts for this report.
        Similar in functionality to RRDView.getDefaultGraphDefs
        """
        graphs = []
        def AppendToGraphs(thing, cmds, title):
            perfServer = thing.device().getPerformanceServer()
            url = perfServer.buildGraphUrlFromCommands(
                                        cmds, drange or self.defaultDateRange)
            graphs.append({
                'title': title,
                'url': url,
                })
        
        def GetThingTitle(thing, postfix=''):
            title = thing.device().id
            if thing != thing.device():
                title += ' %s' % thing.id
            if postfix:
                title += ' - %s' % postfix
            return title
        
        for gg in self.getGraphGroups():
            collection = gg.getCollection()
            things = collection and collection.getDevicesAndComponents()
            graphDef = gg.getGraphDef()
            if not things or not graphDef:
                continue
            if gg.combineDevices:
                cmds = []
                idxOffset = 0
                for thing in things:
                    cmds = graphDef.getGraphCmds(
                                    thing.primaryAq(), 
                                    thing.fullRRDPath(),
                                    includeSetup = not cmds,
                                    includeThresholds = not cmds,
                                    cmds = cmds,
                                    prefix = GetThingTitle(thing),
                                    idxOffset=idxOffset)
                    idxOffset += len(graphDef.graphPoints())
                AppendToGraphs(things[0], cmds, gg.id)
            else:
                for thing in things:
                    cmds = []
                    cmds = graphDef.getGraphCmds(
                                    thing.primaryAq(),
                                    thing.fullRRDPath())
                    AppendToGraphs(thing, cmds, GetThingTitle(thing))
        return graphs


InitializeClass(MultiGraphReport)
