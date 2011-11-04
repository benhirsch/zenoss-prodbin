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

__doc__="""MultiGraphReportClass

MultiGraphReportClass contain MultiGraphReports.
"""

from AccessControl import ClassSecurityInfo
from Globals import DTMLFile
from ReportClass import ReportClass
from Products.ZenRelations.RelSchema import *
from Globals import InitializeClass
from Products.ZenWidgets import messaging
from Products.ZenMessaging.audit import audit
from Products.ZenUtils.Utils import getDisplayType
from Products.ZenUtils.deprecated import deprecated
from Products.ZenModel.MultiGraphReport import MultiGraphReport

@deprecated
def manage_addMultiGraphReportClass(context, id, title = None, REQUEST = None):
    """ Construct a new MultiGraphreportclass
    """
    frc = MultiGraphReportClass(id, title)
    context._setObject(id, frc)
    if REQUEST is not None:
        audit('UI.ReportClass.Add', frc.id, title=title, organizer=context)
        messaging.IMessageSender(self).sendToBrowser(
            'Organizer Created',
            'Report organizer %s was created.' % id
        )
        REQUEST['RESPONSE'].redirect(context.absolute_url() + '/manage_main') 

addMultiGraphReportClass = DTMLFile('dtml/addMultiGraphReportClass',globals())

class MultiGraphReportClass(ReportClass):

    portal_type = meta_type = "MultiGraphReportClass"

    # Remove this relationship after version 2.1
    _relations = ReportClass._relations +  (
        ('graphDefs', 
            ToManyCont(ToOne, 'Products.ZenModel.GraphDefinition', 'reportClass')),
        )
    
    security = ClassSecurityInfo()
    
    def getReportClass(self):
        """ Return the class to instantiate for new report classes
        """
        return MultiGraphReportClass


    security.declareProtected('Manage DMD', 'manage_addMultiGraphReport')
    def manage_addMultiGraphReport(self, id, REQUEST=None):
        """Add a MultiGraph report to this object.
        """
        fr = MultiGraphReport(id)
        self._setObject(id, fr)
        if REQUEST:
            audit('UI.Report.Add', fr.id, reportType=getDisplayType(fr))
            url = '%s/%s/editMultiGraphReport' % (self.getPrimaryUrlPath(), id)
            return REQUEST['RESPONSE'].redirect(url)
        return self._getOb(id)


InitializeClass(MultiGraphReportClass)
