import { http } from '@google-cloud/functions-framework';
import { v1 } from '@google-cloud/dataproc';
const { BatchControllerClient } = v1;

http('helloHttp', async (req, res) => {
  try {
    const client = new BatchControllerClient({
      apiEndpoint: 'us-central1-dataproc.googleapis.com'
    });

    const batchId = `energy-job-${Date.now()}`;

    const request = {
      parent: 'projects/my-project-1-480817/locations/us-central1',
      batchId: batchId,
      batch: {
        pysparkBatch: {
          mainPythonFileUri: 'gs://energy-market-data-platform-480817/spark_transform.py'
        }
      }
    };

    const [operation] = await client.createBatch(request);

    res.status(200).send({
      status: 'submitted',
      batchId: batchId,
      operation: operation.name
    });

  } catch (err) {
    console.error(err);
    res.status(500).send(err.toString());
  }
});
