import itertools
import sys

# Require Python 3.7+ for ordered dictionaries so that the order of the
# generated tests remain the same.
# Usage:
# python3.7 mongos-pin-auto-tests.py > mongos-pin-auto.yml
if sys.version_info[:2] < (3, 7):
    print('ERROR: This script requires Python >= 3.7, not:')
    print(sys.version)
    print('Usage: python3.7 mongos-pin-auto-tests.py > mongos-pin-auto.yml')
    exit(1)

HEADER = '''# Autogenerated tests that transient errors in a transaction unpin the session.
# See mongos-pin-auto-tests.py

description: mongos-pin-auto

schemaVersion: '1.4'

runOnRequirements:
  - minServerVersion: "4.1.8"
    # Note: tests utilize targetedFailPoint, which is incompatible with
    # load-balanced and useMultipleMongoses:true
    topologies: [ sharded ]
    # serverless proxy doesn't append error labels to errors in transactions
    # caused by failpoints (CLOUDP-88216)
    serverless: "forbid"

createEntities:
  - client:
      id: &client0 client0
      useMultipleMongoses: true
      observeEvents: [ commandStartedEvent ]
  - database:
      id: &database0 database0
      client: *client0
      databaseName: &database_name transaction-tests
  - collection:
      id: &collection0 collection0
      database: *database0
      collectionName: &collection_name test
  - session:
      id: &session0 session0
      client: *client0

initialData:
  - collectionName: *collection_name
    databaseName: *database_name
    documents: &data
      - { _id: 1 }
      - { _id: 2 }

tests:
  - description: remain pinned after non-transient Interrupted error on insertOne
    operations:
      - &startTransaction
        object: session0
        name: startTransaction
      - &initialCommand
        object: *collection0
        name: insertOne
        arguments:
          session: *session0
          document: { _id: 3 }
        expectResult: { $$unsetOrMatches: { insertedId: { $$unsetOrMatches: 3 } } }
      - object: testRunner
        name: targetedFailPoint
        arguments:
          session: *session0
          failPoint:
            configureFailPoint: failCommand
            mode: { times: 1 }
            data:
              failCommands: [ "insert" ]
              errorCode: 11601
      - object: *collection0
        name: insertOne
        arguments:
          session: *session0
          document: { _id: 4 }
        expectError:
          errorLabelsOmit: ["TransientTransactionError", "UnknownTransactionCommitResult"]
          errorCodeName: Interrupted
      - &assertSessionPinned
        object: testRunner
        name: assertSessionPinned
        arguments:
          session: *session0
      - &commitTransaction
        object: *session0
        name: commitTransaction
    expectEvents:
      - client: *client0
        events:
          - commandStartedEvent:
              command:
                insert: *collection_name
                documents:
                  - { _id: 3 }
                ordered: true
                readConcern: { $$exists: false }
                lsid: { $$sessionLsid: *session0 }
                txnNumber: { $numberLong: '1' }
                startTransaction: true
                autocommit: false
                writeConcern: { $$exists: false }
              commandName: insert
              databaseName: *database_name
          - commandStartedEvent:
              command:
                insert: *collection_name
                documents:
                  - { _id: 4 }
                ordered: true
                readConcern: { $$exists: false }
                lsid: { $$sessionLsid: *session0 }
                txnNumber: { $numberLong: '1' }
                startTransaction: { $$exists: false }
                autocommit: false
                writeConcern: { $$exists: false }
              commandName: insert
              databaseName: *database_name
          - commandStartedEvent:
              command:
                commitTransaction: 1
                lsid: { $$sessionLsid: *session0 }
                txnNumber: { $numberLong: '1' }
                startTransaction: { $$exists: false }
                autocommit: false
                writeConcern: { $$exists: false }
                recoveryToken: { $$exists: true }
              commandName: commitTransaction
              databaseName: admin
    outcome:
      - collectionName: *collection_name
        databaseName: *database_name
        documents:
          - { _id: 1 }
          - { _id: 2 }
          - { _id: 3 }

  - description: 'unpin after transient error within a transaction'
    operations:
      - *startTransaction
      - *initialCommand
      - object: testRunner
        name: targetedFailPoint
        arguments:
          session: *session0
          failPoint:
            configureFailPoint: failCommand
            mode: { times: 1 }
            data:
              failCommands: [ "insert" ]
              closeConnection: true
      - object: *collection0
        name: insertOne
        arguments:
          session: *session0
          document: { _id: 4 }
        expectError:
          errorLabelsContain: ["TransientTransactionError"]
          errorLabelsOmit: ["UnknownTransactionCommitResult"]
      - &assertSessionUnpinned
        object: testRunner
        name: assertSessionUnpinned
        arguments:
          session: *session0
      - &abortTransaction
        object: *session0
        name: abortTransaction
    expectEvents:
      - client: *client0
        events:
          - commandStartedEvent:
              command:
                insert: *collection_name
                documents:
                  - { _id: 3 }
                ordered: true
                readConcern: { $$exists: false }
                lsid: { $$sessionLsid: *session0 }
                txnNumber: { $numberLong: '1' }
                startTransaction: true
                autocommit: false
                writeConcern: { $$exists: false }
              commandName: insert
              databaseName: *database_name
          - commandStartedEvent:
              command:
                insert: *collection_name
                documents:
                  - { _id: 4 }
                ordered: true
                readConcern: { $$exists: false }
                lsid: { $$sessionLsid: *session0 }
                txnNumber: { $numberLong: '1' }
                startTransaction: { $$exists: false }
                autocommit: false
                writeConcern: { $$exists: false }
              commandName: insert
              databaseName: *database_name
          - commandStartedEvent:
              command:
                abortTransaction: 1
                lsid: { $$sessionLsid: *session0 }
                txnNumber: { $numberLong: '1' }
                startTransaction: { $$exists: false }
                autocommit: false
                writeConcern: { $$exists: false }
                recoveryToken: { $$exists: true }
              commandName: abortTransaction
              databaseName: admin
    outcome: &outcome
      - collectionName: *collection_name
        databaseName: *database_name
        documents: *data

  # The rest of the tests in this file test every operation type against
  # multiple types of transient errors (connection and error code).'''

TEMPLATE = '''
  - description: {test_name} {error_name} error on {op_name} {command_name}
    operations:
      - *startTransaction
      - *initialCommand
      - name: targetedFailPoint
        object: testRunner
        arguments:
          session: *session0
          failPoint:
            configureFailPoint: failCommand
            mode: {{times: 1}}
            data:
              failCommands: ["{command_name}"]
              {error_data}
      - name: {op_name}
        object: {object_name}
        arguments:
          session: *session0
          {op_args}
        expectError:
          {error_labels}: ["TransientTransactionError"]
      - *{assertion}
      - *abortTransaction
    outcome: *outcome
'''


# Maps from op_name to (command_name, object_name, op_args)
OPS = {
    # Write ops:
    'insertOne': ('insert', '*collection0', r'document: { _id: 4 }'),
    'insertMany': ('insert', '*collection0', r'documents: [ { _id: 4 }, { _id: 5 } ]'),
    'updateOne': ('update', '*collection0', r'''filter: { _id: 1 }
          update: { $inc: { x: 1 } }'''),
    'replaceOne': ('update', '*collection0', r'''filter: { _id: 1 }
          replacement: { y: 1 }'''),
    'updateMany': ('update', '*collection0', r'''filter: { _id: { $gte: 1 } }
          update: {$set: { z: 1 } }'''),
    'deleteOne': ('delete', '*collection0', r'filter: { _id: 1 }'),
    'deleteMany': ('delete', '*collection0', r'filter: { _id: { $gte: 1 } }'),
    'findOneAndDelete': ('findAndModify', '*collection0', r'filter: { _id: 1 }'),
    'findOneAndUpdate': ('findAndModify', '*collection0', r'''filter: { _id: 1 }
          update: { $inc: { x: 1 } }
          returnDocument: Before'''),
    'findOneAndReplace': ('findAndModify', '*collection0', r'''filter: { _id: 1 }
          replacement: { y: 1 }
          returnDocument: Before'''),
    # Bulk write insert/update/delete:
    'bulkWrite insert': ('insert', '*collection0', r'''requests:
            - insertOne:
                document: { _id: 1 }'''),
    'bulkWrite update': ('update', '*collection0', r'''requests:
            - updateOne:
                filter: { _id: 1 }
                update: { $set: { x: 1 } }'''),
    'bulkWrite delete': ('delete', '*collection0', r'''requests:
            - deleteOne:
                filter: { _id: 1 }'''),
    # Read ops:
    'find': ('find', '*collection0', r'filter: { _id: 1 }'),
    'countDocuments': ('aggregate', '*collection0', r'filter: {}'),
    'aggregate': ('aggregate', '*collection0', r'pipeline: []'),
    'distinct': ('distinct', '*collection0', r'''fieldName: _id
          filter: {}'''),
    # runCommand:
    'runCommand': ('insert', '*database0', r'''commandName: insert
          command:
            insert: *collection_name
            documents:
              - { _id : 1 }'''),
    # clientBulkWrite:
    'clientBulkWrite': ('bulkWrite', '*client0', r'''models:
          - insertOne:
              namespace: database0.collection0
              document: { _id: 8, x: 88 }'''),
}

# Maps from error_name to error_data.
NON_TRANSIENT_ERRORS = {
    'Interrupted': 'errorCode: 11601',
}

# Maps from error_name to error_data.
TRANSIENT_ERRORS = {
    'connection': 'closeConnection: true',
    'ShutdownInProgress': 'errorCode: 91',
}


def create_pin_test(op_name, error_name):
    test_name = 'remain pinned after non-transient'
    assertion = 'assertSessionPinned'
    error_labels = 'errorLabelsOmit'
    command_name, object_name, op_args = OPS[op_name]
    error_data = NON_TRANSIENT_ERRORS[error_name]
    if op_name.startswith('bulkWrite'):
        op_name = 'bulkWrite'
    test = TEMPLATE.format(**locals())
    if op_name == 'clientBulkWrite':
        test += '    runOnRequirements:\n'
        test += '      - minServerVersion: "8.0" # `bulkWrite` added to server 8.0"\n'
    return test


def create_unpin_test(op_name, error_name):
    test_name = 'unpin after transient'
    assertion = 'assertSessionUnpinned'
    error_labels = 'errorLabelsContain'
    command_name, object_name, op_args = OPS[op_name]
    error_data = TRANSIENT_ERRORS[error_name]
    if op_name.startswith('bulkWrite'):
        op_name = 'bulkWrite'
    test = TEMPLATE.format(**locals())
    if op_name == 'clientBulkWrite':
        test += '    runOnRequirements:\n'
        test += '      - minServerVersion: "8.0" # `bulkWrite` added to server 8.0"\n'
    return test
        


tests = []
for op_name, error_name in itertools.product(OPS, NON_TRANSIENT_ERRORS):
    tests.append(create_pin_test(op_name, error_name))
for op_name, error_name in itertools.product(OPS, TRANSIENT_ERRORS):
    tests.append(create_unpin_test(op_name, error_name))

print(HEADER)
print(''.join(tests))
