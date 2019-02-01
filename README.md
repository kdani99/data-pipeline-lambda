# data-pipeline-lambda
Testing/dev repo for lambda function for data pipeline

Run `pip install -r requirements.txt`

Run `sam local invoke -t "imageset-converter-lambda.yaml" -e test_event.json --env-vars env.json` to test.
Writes to test Bucket and Table by default only if you include the `--env-vars` tag. 

Run `python unit_test_.py` to unit test. 

When finished developping, copy and paste the lambda function into the inline editor on the Lambda Management Console (https://us-east-2.console.aws.amazon.com/lambda/home?region=us-east-2#/functions/imageset-converter-lambda?tab=graph). If you test at this stage using the "Test" button on the upper right, it will write to production buckets and table. Use the Environment Variables section of the console to write to either the test or production bucket/table. 

Test Table: metadata_test
Production Table: metadata

Test Bucket:avi-image-label-npz-test
Production Bucket:avi-image-label-npz

When ready to push to production, publish a new version, using Actions > Publish new version. Add a short note to describe changes. 

Troubleshooting:
- `HeadObject not found error. ` Make sure that the paths given in the configured test events (both local and online) exist. 
- Timeout issues - When running locally, the time limit is set to 30 seconds. For production it is set to 20 seconds. It has happened that increasing the time limit allows the operation to complete successfully. Use best judgement in changing these limits. 
