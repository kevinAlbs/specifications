# CRUD Tests

## Introduction

The YAML and JSON files in this directory tree are platform-independent tests that drivers can use to prove their
conformance to the CRUD spec.

Running these integration tests will require a running MongoDB server or cluster with server versions 2.6.0 or later.
Some tests have specific server version requirements as noted by the `runOn` section, if provided.

### Subdirectories for Test Formats

This document describes a legacy format for CRUD tests: legacy-v1, which dates back to the first version of the CRUD
specification. New CRUD tests should be written in the
[unified test format](../../unified-test-format/unified-test-format.md) and placed under `unified/`. Until such time
that all original tests have been ported to the unified test format, tests in each format will be grouped in their own
subdirectory:

- `v1/`: Legacy-v1 format tests
- `unified/`: Tests using the [unified test format](../../unified-test-format/unified-test-format.md)

Since some drivers may not have a unified test runner capable of executing tests in all two formats, segregating tests
in this manner will make it easier for drivers to sync and feed test files to different test runners.

### Legacy-v1 Test Format for Single Operations

*Note: this section pertains to test files in the "v1" directory.*

The test format above supports both multiple operations and APM expectations, and is consistent with the formats used by
other specifications. Previously, the CRUD spec tests used a simplified format that only allowed for executing a single
operation. Notable differences from the legacy-v2 format are as follows:

- Instead of a `tests[i].operations` array, a single operation was defined as a document in `tests[i].operation`. That
  document consisted of only the `name`, `arguments`, and an optional `object` field.
- Instead of `error` and `result` fields within each element in the `tests[i].operations` array, the single operation's
  error and result were defined under the `tests[i].outcome.error` and `tests[i].outcome.result` fields.
- Instead of a top-level `runOn` field, server requirements are denoted by separate top-level `minServerVersion`,
  `maxServerVersion`, and `serverless` fields. The minimum server version is an inclusive lower bound for running the
  test. The maximum server version is an exclusive upper bound for running the test. If a field is not present, it
  should be assumed that there is no corresponding bound on the required server version. The `serverless` requirement
  behaves the same as the `serverless` field of the
  [unified test format's runOnRequirement](../../unified-test-format/unified-test-format.md#runonrequirement).

The legacy-v1 format should not conflict with the newer, multi-operation format used by other specs (e.g. Transactions).
It is possible to create a unified test runner capable of executing both legacy formats (as some drivers do).

## Error Assertions for Bulk Write Operations

When asserting errors (e.g. `errorContains`, `errorCodeName`) for bulk write operations, the test harness should inspect
the `writeConcernError` and/or `writeErrors` properties of the bulk write exception. This may not be needed for
`errorContains` if a driver concatenates all write and write concern error messages into the bulk write exception's
top-level message.

## Test Runner Implementation

This section provides guidance for implementing a test runner for legacy-v1 tests. See the
[unified test format spec](../../unified-test-format/unified-test-format.md) for how to run tests under `unified/`.

Before running the tests:

- Create a global MongoClient (`globalMongoClient`) and connect to the server. This client will be used for executing
  meta operations, such as checking server versions and preparing data fixtures.

For each test file:

- Using `globalMongoClient`, check that the current server version satisfies one of the configurations provided in the
  top-level `runOn` field in the test file (if applicable). If the requirements are not satisfied, the test file should
  be skipped.
- Determine the collection and database under test, utilizing the top-level `collection_name` and/or `database_name`
  fields if present.
- For each element in the `tests` array:
  - Using `globalMongoClient`, ensure that the collection and/or database under test is in a "clean" state, as needed.
    This may be accomplished by dropping the database; however, drivers may also decide to drop individual collections
    as needed (this may be more performant).
  - If the top-level `data` field is present in the test file, insert the corresponding data into the collection under
    test using `globalMongoClient`.
  - If the the `failPoint` field is present, use `globalMongoClient` to configure the fail point on the primary server.
    See [Server Fail Point](../../transactions/tests#server-fail-point) in the Transactions spec test documentation for
    more information.
  - Create a local MongoClient (`localMongoClient`) and connect to the server. This client will be used for executing
    the test case.
    - If `clientOptions` is present, those options should be used to create the client. Drivers MAY merge these options
      atop existing defaults (e.g. reduced `serverSelectionTimeoutMS` value for faster test failures) at their own
      discretion.
  - Activate command monitoring for `localMongoClient` and begin capturing events. Note that some events may need to be
    filtered out if the driver uses global listeners or reports internal commands (e.g. `hello`, legacy hello,
    authentication).
  - For each element in the `operations` array:
    - Using `localMongoClient`, select the appropriate `object` to execute the operation. Default to the collection
      under test if this field is not present.
      - If `collectionOptions` is present, those options should be used to construct the collection object.
    - Given the `name` and `arguments`, execute the operation on the object under test. Capture the result of the
      operation, if any, and observe whether an error occurred. If an error is encountered that includes a result (e.g.
      BulkWriteException), extract the result object.
    - If `error` is present and true, assert that the operation encountered an error. Otherwise, assert that no error
      was encountered.
    - if `result` is present, assert that it matches the operation's result.
  - Deactivate command monitoring for `localMongoClient`.
  - If the `expectations` array is present, assert that the sequence of emitted CommandStartedEvents from executing the
    operation(s) matches the sequence of `command_started_event` objects in the `expectations` array.
  - If the `outcome` field is present, assert the contents of the specified collection using `globalMongoClient`. Note
    the server does not guarantee that documents returned by a find command will be in inserted order. This find MUST
    sort by `{_id:1}`.

### Evaluating Matches

The expected values for results (e.g. `result` for an operation operation, `command_started_event.command`, elements in
`outcome.data`) are written in [Extended JSON](../../extended-json.rst). Drivers may adopt any of the following
approaches to comparisons, as long as they are consistent:

- Convert `actual` to Extended JSON and compare to `expected`
- Convert `expected` and `actual` to BSON, and compare them
- Convert `expected` and `actual` to native representations, and compare them

#### Extra Fields in Actual Documents

When comparing `actual` and `expected` *documents*, drivers should permit `actual` documents to contain additional
fields not present in `expected`. For example, the following documents match:

- `expected` is `{ "x": 1 }`
- `actual` is `{ "_id": { "$oid" : "000000000000000000000001" }, "x": 1 }`

In this sense, `expected` may be a subset of `actual`. It may also be helpful to think of `expected` as a form of query
criteria. The intention behind this rule is that it is not always feasible for the test to express all fields in the
expected document(s) (e.g. session and cluster time information in a `command_started_event.command` document).

This rule for allowing extra fields in `actual` only applies for values that correspond to a document. For instance, an
actual result of `[1, 2, 3, 4]` for a `distinct` operation would not match an expected result of `[1, 2, 3]`. Likewise
with the `find` operation, this rule would only apply when matching documents *within* the expected result array and
actual cursor.

Note that in the case of result objects for some CRUD operations, `expected` may condition additional, optional fields
(see: [Optional Fields in Expected Result Objects](#optional-fields-in-expected-result-objects)).

#### Fields that must NOT be present in Actual Documents

Some command-started events in `expectations` include `null` values for optional fields such as `allowDiskUse`. Tests
MUST assert that the actual command **omits** any field that has a `null` value in the expected command.

#### Optional Fields in Expected Result Objects

Some `expected` results may include fields that are optional in the CRUD specification, such as `insertedId` (for
InsertOneResult), `insertedIds` (for InsertManyResult), and `upsertedCount` (for UpdateResult). Drivers that do not
implement these fields should ignore them when comparing `actual` with `expected`.

## Prose Tests

The following tests have not yet been automated, but MUST still be tested.

### 1. WriteConcernError.details exposes writeConcernError.errInfo

Test that `writeConcernError.errInfo` in a command response is propagated as `WriteConcernError.details` (or equivalent)
in the driver.

Using a 4.0+ server, set the following failpoint:

```javascript
{
  "configureFailPoint": "failCommand",
  "data": {
    "failCommands": ["insert"],
    "writeConcernError": {
      "code": 100,
      "codeName": "UnsatisfiableWriteConcern",
      "errmsg": "Not enough data-bearing nodes",
      "errInfo": {
        "writeConcern": {
          "w": 2,
          "wtimeout": 0,
          "provenance": "clientSupplied"
        }
      }
    }
  },
  "mode": { "times": 1 }
}
```

Then, perform an insert operation and assert that a WriteConcernError occurs and that its `details` property is both
accessible and matches the `errInfo` object from the failpoint.

### 2. WriteError.details exposes writeErrors\[\].errInfo

Test that `writeErrors[].errInfo` in a command response is propagated as `WriteError.details` (or equivalent) in the
driver.

Using a 5.0+ server, create a collection with
[document validation](https://www.mongodb.com/docs/manual/core/schema-validation/) like so:

```javascript
{
  "create": "test",
  "validator": {
    "x": { $type: "string" }
  }
}
```

Enable [command monitoring](../../command-logging-and-monitoring/command-logging-and-monitoring.rst) to observe
CommandSucceededEvents. Then, insert an invalid document (e.g. `{x: 1}`) and assert that a WriteError occurs, that its
code is `121` (i.e. DocumentValidationFailure), and that its `details` property is accessible. Additionally, assert that
a CommandSucceededEvent was observed and that the `writeErrors[0].errInfo` field in the response document matches the
WriteError's `details` property.

### 3. `MongoClient.bulkWrite` batch splits a `writeModels` input with greater than `maxWriteBatchSize` operations

Test that `MongoClient.bulkWrite` properly handles `writeModels` inputs containing a number of writes greater than
`maxWriteBatchSize`.

This test must only be run on 8.0+ servers.

Construct a `MongoClient` (referred to as `client`) with
[command monitoring](../../command-logging-and-monitoring/command-logging-and-monitoring.rst) enabled to observe
CommandStartedEvents. Perform a `hello` command using `client` and record the `maxWriteBatchSize` value contained in the
response. Then, construct the following write model (referred to as `writeModel`):

```json
InsertOne: {
  "namespace": "db.coll",
  "document": { "a": "b" }
}
```

#### Test maximum in one batch

Construct a list of write models (referred to as `models`) with `writeModel` repeated `maxWriteBatchSize` times.
Execute `bulkWrite` on `client` with `models`. Assert that the bulk write succeeds and returns a `BulkWriteResult`
with an `insertedCount` value of `maxWriteBatchSize`.

Assert that one CommandStartedEvent (referred to as `firstEvent`) was observed for the `bulkWrite` command.
Assert that the length of `firstEvent.command.ops` is `maxWriteBatchSize`.

#### Test two batches

Construct a list of write models (referred to as `models`) with `writeModel` repeated `maxWriteBatchSize + 1` times.
Execute `bulkWrite` on `client` with `models`. Assert that the bulk write succeeds and returns a `BulkWriteResult`
with an `insertedCount` value of `maxWriteBatchSize + 1`.

Assert that two CommandStartedEvents (referred to as `firstEvent` and `secondEvent`) were observed for the `bulkWrite` command.
Assert that the length of `firstEvent.command.ops` is `maxWriteBatchSize`. Assert that the length of `secondEvent.command.ops`
is 1. If the driver exposes `operationId`s in its CommandStartedEvents, assert that `firstEvent.operationId` is equal to
`secondEvent.operationId`.

### 4. `MongoClient.bulkWrite` batch splits when an `ops` payload exceeds `maxMessageSizeBytes`

Test that `MongoClient.bulkWrite` properly handles a `writeModels` input which constructs an `ops` array larger than
`maxMessageSizeBytes`.

This test must only be run on 8.0+ servers.

Construct a `MongoClient` (referred to as `client`) with
[command monitoring](../../command-logging-and-monitoring/command-logging-and-monitoring.rst) enabled to observe
CommandStartedEvents. Perform a `hello` command using `client` and record the following values from the response:
`maxBsonObjectSize` and `maxMessageSizeBytes`. Then, construct the following document (referred to as `document`):

```json
{
  "a": "b".repeat(maxBsonObjectSize - 500)
}
```

Construct the following write model (referred to as `model`):

```json
InsertOne: {
  "namespace": "db.coll",
  "document": document
}
```

#### Test maximum in one batch

Use the following calculation to determine the number of inserts that should be provided to `MongoClient.bulkWrite`:
`maxMessageSizeBytes / maxBsonObjectSize` (referred to as `numModels`). This number is intended to be close
to the maximum before splitting.

Construct as list of write models (referred to as `models`) with `model` repeated `numModels` times. Then execute
`bulkWrite` on `client` with `models`. Assert that the bulk write succeeds and returns a `BulkWriteResult` with
an `insertedCount` value of `numModels`.

Assert that one CommandStartedEvents (referred to as `firstEvent`) was observed. Assert that the length of
`firstEvent.command.ops` is equal to `numModels`.

#### Test two batches

Use the following calculation to determine the number of inserts that should be provided to `MongoClient.bulkWrite`:
`maxMessageSizeBytes / maxBsonObjectSize + 1` (referred to as `numModels`). This number ensures that the inserts
provided to `MongoClient.bulkWrite` will require multiple `bulkWrite` commands to be sent to the server.

Construct as list of write models (referred to as `models`) with `model` repeated `numModels` times. Then execute
`bulkWrite` on `client` with `models`. Assert that the bulk write succeeds and returns a `BulkWriteResult` with
an `insertedCount` value of `numModels`.

Assert that two CommandStartedEvents (referred to as `firstEvent` and `secondEvent`) were observed. Assert that the sum
of the lengths of `firstEvent.command.ops` and `secondEvent.command.ops` is equal to `numModels`. If the driver exposes
`operationId`s in its CommandStartedEvents, assert that `firstEvent.operationId` is equal to `secondEvent.operationId`.

### 5. `MongoClient.bulkWrite` returns error for unacknowledged too-large insert

This test must only be run on 8.0+ servers.

Construct a `MongoClient` (referred to as `client`).

Perform a `hello` command using `client` and record the following values from the response: `maxBsonObjectSize`.

Then, construct the following document (referred to as `document`):

```json
{
  "a": "b".repeat(maxBsonObjectSize)
}
```

#### With insert

Construct the following write model (referred to as `model`):

```json
InsertOne: {
  "namespace": "db.coll",
  "document": document
}
```

Construct as list of write models (referred to as `models`) with the one `model`.

Call `MongoClient.bulkWrite` with `models` and `BulkWriteOptions.writeConcern` set to an unacknowledged write concern.

Expect a client-side error due the size.

#### With replace

Construct the following write model (referred to as `model`):

```json
ReplaceOne: {
  "namespace": "db.coll",
  "filter": {},
  "replacement": document
}
```

Construct as list of write models (referred to as `models`) with the one `model`.

Call `MongoClient.bulkWrite` with `models` and `BulkWriteOptions.writeConcern` set to an unacknowledged write concern.

Expect a client-side error due the size.

### 6. `MongoClient.bulkWrite` collects `writeErrors` across batches

Construct a `MongoClient` (referred to as `client`) with
[command monitoring](../../command-logging-and-monitoring/command-logging-and-monitoring.rst) enabled to observe
CommandStartedEvents.

Perform a `hello` command using `client` and record the following values from the response: `maxWriteBatchSize`.

Construct a list of write models (referred to as `models`) as follows:

Append this model twice:

```json
InsertOne: {
  "namespace": "db.coll",
  "document": { "_id": 0 }
}
```

Append `maxWriteBatchSize` copies of this model:

```json
InsertOne: {
  "namespace": "db.coll",
  "document": { "foo": "bar" }
}
```

Append this model twice:

```json
InsertOne: {
  "namespace": "db.coll",
  "document": { "_id": 1 }
}
```

Call `MongoClient.bulkWrite` with `models` and `BulkWriteOptions.ordered` set to `false`.

Assert that two CommandStartedEvents were observed.

Expect a `BulkWriteException` with a map of `writeConcern` errors containing a total of two entries (for duplicate keys).

