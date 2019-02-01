# data-pipeline-lambda
Testing/dev repo for lambda function for data pipeline

Run pip install -r requirements.txt
Run sam local invoke -t "imageset-converter-lambda.yaml" -e test_event.json to test.
Writes to test Bucket and production Table by default, change where applicable depending on development vs production.
