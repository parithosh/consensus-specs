# EIP-7594 -- Networking

**Notice**: This document is a work-in-progress for researchers and implementers.

## Table of contents

<!-- TOC -->
<!-- START doctoc generated TOC please keep comment here to allow auto update -->
<!-- DON'T EDIT THIS SECTION, INSTEAD RE-RUN doctoc TO UPDATE -->

- [Modifications in EIP-7594](#modifications-in-eip-7594)
  - [Preset](#preset)
  - [Configuration](#configuration)
  - [Containers](#containers)
    - [`DataColumnIdentifier`](#datacolumnidentifier)
  - [Helpers](#helpers)
      - [`verify_data_column_sidecar_kzg_proofs`](#verify_data_column_sidecar_kzg_proofs)
      - [`verify_data_column_sidecar_inclusion_proof`](#verify_data_column_sidecar_inclusion_proof)
      - [`compute_subnet_for_data_column_sidecar`](#compute_subnet_for_data_column_sidecar)
  - [The gossip domain: gossipsub](#the-gossip-domain-gossipsub)
    - [Topics and messages](#topics-and-messages)
      - [Blob subnets](#blob-subnets)
        - [Deprecated `blob_sidecar_{subnet_id}`](#deprecated-blob_sidecar_subnet_id)
        - [`data_column_sidecar_{subnet_id}`](#data_column_sidecar_subnet_id)
  - [The Req/Resp domain](#the-reqresp-domain)
    - [Messages](#messages)
      - [DataColumnSidecarsByRoot v1](#datacolumnsidecarsbyroot-v1)
  - [The discovery domain: discv5](#the-discovery-domain-discv5)
    - [ENR structure](#enr-structure)
      - [`custody_subnet_count`](#custody_subnet_count)

<!-- END doctoc generated TOC please keep comment here to allow auto update -->
<!-- /TOC -->

## Modifications in EIP-7594

### Preset

| Name | Value | Description |
| - | - | - |
| `KZG_COMMITMENTS_INCLUSION_PROOF_DEPTH` | `uint64(floorlog2(get_generalized_index(BeaconBlockBody, 'blob_kzg_commitments')))` (= 4) | <!-- predefined --> Merkle proof index for `blob_kzg_commitments` |


### Configuration

*[New in Deneb:EIP4844]*

| Name                                     | Value                             | Description                                                         |
|------------------------------------------|-----------------------------------|---------------------------------------------------------------------|
| `MAX_REQUEST_DATA_COLUMN_SIDECARS`       | `MAX_REQUEST_BLOCKS_DENEB * NUMBER_OF_COLUMNS` | Maximum number of data column sidecars in a single request  |
| `MIN_EPOCHS_FOR_DATA_COLUMN_SIDECARS_REQUESTS`  | `2**12` (= 4096 epochs, ~18 days) | The minimum epoch range over which a node must serve data column sidecars  |

### Containers

#### `DataColumnIdentifier`

```python
class DataColumnIdentifier(Container):
    block_root: Root
    index: ColumnIndex
```

### Helpers

##### `verify_data_column_sidecar_kzg_proofs`

```python
def verify_data_column_sidecar_kzg_proofs(sidecar: DataColumnSidecar) -> bool:
    """
    Verify if the proofs are correct
    """
    assert sidecar.index < NUMBER_OF_COLUMNS
    assert len(sidecar.column) == len(sidecar.kzg_commitments) == len(sidecar.kzg_proofs)
    row_ids = [RowIndex(i) for i in range(len(sidecar.column))]

    # KZG batch verifies that the cells match the corresponding commitments and proofs
    return verify_cell_proof_batch(
        row_commitments=sidecar.kzg_commitments,
        row_indices=row_ids,  # all rows
        column_indices=[sidecar.index],
        cells=sidecar.column,
        proofs=sidecar.kzg_proofs,
    )
```

##### `verify_data_column_sidecar_inclusion_proof`

```python
def verify_data_column_sidecar_inclusion_proof(sidecar: DataColumnSidecar) -> bool:
    """
    Verify if the given KZG commitments included in the given beacon block.
    """
    gindex = get_subtree_index(get_generalized_index(BeaconBlockBody, 'blob_kzg_commitments'))
    return is_valid_merkle_branch(
        leaf=hash_tree_root(sidecar.kzg_commitments),
        branch=sidecar.kzg_commitments_inclusion_proof,
        depth=KZG_COMMITMENTS_INCLUSION_PROOF_DEPTH,
        index=gindex,
        root=sidecar.signed_block_header.message.body_root,
    )
```

##### `compute_subnet_for_data_column_sidecar`

```python
def compute_subnet_for_data_column_sidecar(column_index: ColumnIndex) -> SubnetID:
    return SubnetID(column_index % DATA_COLUMN_SIDECAR_SUBNET_COUNT)
```

### The gossip domain: gossipsub

Some gossip meshes are upgraded in the EIP-7594 fork to support upgraded types.

#### Topics and messages

##### Blob subnets

###### Deprecated `blob_sidecar_{subnet_id}`

`blob_sidecar_{subnet_id}` is deprecated.

###### `data_column_sidecar_{subnet_id}`

This topic is used to propagate column sidecars, where each column maps to some `subnet_id`.

The *type* of the payload of this topic is `DataColumnSidecar`.

The following validations MUST pass before forwarding the `sidecar: DataColumnSidecar` on the network, assuming the alias `block_header = sidecar.signed_block_header.message`:

- _[REJECT]_ The sidecar's index is consistent with `NUMBER_OF_COLUMNS` -- i.e. `sidecar.index < NUMBER_OF_COLUMNS`.
- _[REJECT]_ The sidecar is for the correct subnet -- i.e. `compute_subnet_for_data_column_sidecar(sidecar.index) == subnet_id`.
- _[IGNORE]_ The sidecar is not from a future slot (with a `MAXIMUM_GOSSIP_CLOCK_DISPARITY` allowance) -- i.e. validate that `block_header.slot <= current_slot` (a client MAY queue future sidecars for processing at the appropriate slot).
- _[IGNORE]_ The sidecar is from a slot greater than the latest finalized slot -- i.e. validate that `block_header.slot > compute_start_slot_at_epoch(state.finalized_checkpoint.epoch)`
- _[REJECT]_ The proposer signature of `sidecar.signed_block_header`, is valid with respect to the `block_header.proposer_index` pubkey.
- _[IGNORE]_ The sidecar's block's parent (defined by `block_header.parent_root`) has been seen (via both gossip and non-gossip sources) (a client MAY queue sidecars for processing once the parent block is retrieved).
- _[REJECT]_ The sidecar's block's parent (defined by `block_header.parent_root`) passes validation.
- _[REJECT]_ The sidecar is from a higher slot than the sidecar's block's parent (defined by `block_header.parent_root`).
- _[REJECT]_ The current finalized_checkpoint is an ancestor of the sidecar's block -- i.e. `get_checkpoint_block(store, block_header.parent_root, store.finalized_checkpoint.epoch) == store.finalized_checkpoint.root`.
- _[REJECT]_ The sidecar's `kzg_commitments` field inclusion proof is valid as verified by `verify_data_column_sidecar_inclusion_proof(sidecar)`.
- _[REJECT]_ The sidecar's column data is valid as verified by `verify_data_column_sidecar_kzg_proofs(sidecar)`.
- _[IGNORE]_ The sidecar is the first sidecar for the tuple `(block_header.slot, block_header.proposer_index, sidecar.index)` with valid header signature, sidecar inclusion proof, and kzg proof.
- _[REJECT]_ The sidecar is proposed by the expected `proposer_index` for the block's slot in the context of the current shuffling (defined by `block_header.parent_root`/`block_header.slot`).
  If the `proposer_index` cannot immediately be verified against the expected shuffling, the sidecar MAY be queued for later processing while proposers for the block's branch are calculated -- in such a case _do not_ `REJECT`, instead `IGNORE` this message.

*Note:* In the `verify_data_column_sidecar_inclusion_proof(sidecar)` check, for all the sidecars of the same block, it verifies against the same set of `kzg_commitments` of the given beacon block. Client can choose to cache the result of the arguments tuple `(sidecar.kzg_commitments, sidecar.kzg_commitments_inclusion_proof, sidecar.signed_block_header)`.

### The Req/Resp domain

#### Messages

##### DataColumnSidecarsByRoot v1

**Protocol ID:** `/eth2/beacon_chain/req/data_column_sidecars_by_root/1/`

*[New in EIP7594]*

The `<context-bytes>` field is calculated as `context = compute_fork_digest(fork_version, genesis_validators_root)`:

[1]: # (eth2spec: skip)

| `fork_version` | Chunk SSZ type |
| - | - |
| `EIP7594_FORK_VERSION` | `eip7594.DataColumnSidecar` |

Request Content:

```
(
  List[DataColumnIdentifier, MAX_REQUEST_DATA_COLUMN_SIDECARS]
)
```

Response Content:

```
(
    List[DataColumnSidecar, MAX_REQUEST_DATA_COLUMN_SIDECARS]
)
```

Requests sidecars by block root and index.
The response is a list of `DataColumnIdentifier` whose length is less than or equal to the number of requests.
It may be less in the case that the responding peer is missing blocks or sidecars.

Before consuming the next response chunk, the response reader SHOULD verify the data column sidecar is well-formatted, has valid inclusion proof, and is correct w.r.t. the expected KZG commitments through `verify_data_column_sidecar_kzg_proofs`.

No more than `MAX_REQUEST_DATA_COLUMN_SIDECARS` may be requested at a time.

The response MUST consist of zero or more `response_chunk`.
Each _successful_ `response_chunk` MUST contain a single `DataColumnSidecar` payload.

Clients MUST support requesting sidecars since `minimum_request_epoch`, where `minimum_request_epoch = max(finalized_epoch, current_epoch - MIN_EPOCHS_FOR_DATA_COLUMN_SIDECARS_REQUESTS, EIP7594_FORK_EPOCH)`. If any root in the request content references a block earlier than `minimum_request_epoch`, peers MAY respond with error code `3: ResourceUnavailable` or not include the data column sidecar in the response.

Clients MUST respond with at least one sidecar, if they have it.
Clients MAY limit the number of blocks and sidecars in the response.

Clients SHOULD include a sidecar in the response as soon as it passes the gossip validation rules.
Clients SHOULD NOT respond with sidecars related to blocks that fail gossip validation rules.
Clients SHOULD NOT respond with sidecars related to blocks that fail the beacon chain state transition

### The discovery domain: discv5

#### ENR structure

##### `custody_subnet_count`

A new field is added to the ENR under the key `custody_subnet_count` to facilitate custody data column discovery.

| Key                    | Value        |
|:-----------------------|:-------------|
| `custody_subnet_count` | SSZ `uint64` |
