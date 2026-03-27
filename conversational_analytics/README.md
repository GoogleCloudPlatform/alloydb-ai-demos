# AlloyDB Conversational Analytics Examples

This directory contains examples demonstrating how to use the Conversational Analytics API with Google Cloud AlloyDB. These examples show how to build data agents that can understand natural language questions and generate SQL queries to retrieve answers from your AlloyDB database.

**Prerequisites:**

*   A Google Cloud Project with an active AlloyDB cluster and instance.
*   A database created within your AlloyDB instance.
*   The Cloud AI Companion API enabled.
*   Appropriate IAM permissions to access AlloyDB and the Conversational Analytics API. See [Conversational Analytics API access control with IAM](https://docs.cloud.google.com/gemini/data-agents/conversational-analytics-api/access-control) for details.
*   `gcloud` CLI installed and configured.
*   Python 3.7+ (for SDK examples).

## Examples

This guide provides examples for interacting with the API using both the Python Client Library (SDK) and HTTP requests (curl).

**Note:** According to the [documentation](https://docs.cloud.google.com/gemini/data-agents/conversational-analytics-api/overview), building data agents using HTTP or the Python SDK and rendering visualizations is not fully supported for database data sources (including AlloyDB) in the same way as for BigQuery or Looker. The primary method for database interaction is often via the `QueryData` method. The examples below illustrate the general structure, but specific API calls for agent creation/chat might differ.

