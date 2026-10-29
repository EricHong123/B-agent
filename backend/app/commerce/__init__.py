"""B-agent's host for the vendored commerce agents (``commerce/``).

The buyer assistant runs the shopping agent over the B2B catalog, trade terms, RFQ
basket and fulfillment orders; the operations assistant runs the merchant agent over
the catalog, campaigns, pipeline metrics and a durable staged-change ledger. Both use
the packages' prompts, tool contracts, gates and turn loops unchanged; this package
supplies the backends, storage, identity and model client.
"""
