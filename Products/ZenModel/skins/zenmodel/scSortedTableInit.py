## Script (Python) "scSortedTableGetBatch"
##parameters=tableName,defaultSort="primarySortKey",defaultSortRule='cmp',batchSize=20,usebatch=1,sortedSence='asc'
##bind context=context
##title=Initialize sorted table session data

request=context.REQUEST
session=request.SESSION

if hasattr(context, 'userDefaultBatchSize'):
    defaultBatchSize = context.userDefaultBatchSize
elif hasattr(context, 'defaultBatchSize'):
    defaultBatchSize = context.defaultBatchSize
else:
    defaultBatchSize = batchSize

tableatts = ( 'sortedHeader',
            'sortedSence',
            'sortRule',
            'start',
            'filter',
            'filterattribute',
            'negatefilter',
            'severity',
            'batchSize',
            )

if (session.has_key(tableName) 
    and session[tableName].has_key('url')
    and session[tableName]['url']==request.URL):
    sortedTableState = session[tableName]
    if request.has_key('tableName') and request['tableName'] == tableName:
        for attname in tableatts:
            if request.has_key(attname):
                sortedTableState[attname] = request[attname]
        if request.has_key('batchSize'):
            sortedTableState['start'] = 0
        if not request.has_key("negatefilter"):
            sortedTableState['negatefilter'] = 0
else:
    sortedTableState = {
        'start' : 0,
        'url' : request.URL,
        'sortedHeader' : defaultSort,
        'sortRule' : defaultSortRule,
        'sortedSence' : sortedSence,
        'batchSize' : defaultBatchSize,
        }

session[tableName] = sortedTableState
