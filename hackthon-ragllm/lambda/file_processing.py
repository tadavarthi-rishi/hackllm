import boto3
import os
import json
import pinecone
from langchain.embeddings.openai import OpenAIEmbeddings
from langchain.vectorstores import Pinecone
from langchain.schema import Document
from botocore.exceptions import ClientError

# Initialize AWS clients
s3_client = boto3.client('s3')
textract = boto3.client('textract')
secrets_manager = boto3.client('secretsmanager')

# Function to retrieve secrets from AWS Secrets Manager
def get_secret(secret_name):
    try:
        secret_response = secrets_manager.get_secret_value(SecretId=secret_name)
        secret = secret_response['SecretString']
        return json.loads(secret)
    except ClientError as e:
        raise Exception(f"Unable to retrieve secret {secret_name}: {e}")

def lambda_handler(event, context):
    # Retrieve secrets for OpenAI and Pinecone API keys
    openai_secret = get_secret(os.getenv('OPENAI_SECRET_NAME'))
    pinecone_secret = get_secret(os.getenv('PINECONE_SECRET_NAME'))

    openai_api_key = openai_secret['api_key']
    pinecone_api_key = pinecone_secret['api_key']
    pinecone_environment = pinecone_secret['environment']

    # Extract S3 bucket name and object key from event
    bucket = os.getenv('BUCKET_NAME')
    for record in event['Records']:
        key = record.s3.object.key

        # Extract text from PDF using Textract
        response = textract.analyze_document(
            Document={'S3Object': {'Bucket': bucket, 'Name': key}},
            FeatureTypes=['TABLES', 'FORMS']
        )

        extracted_text = ''
        for block in response['Blocks']:
            if block['BlockType'] == 'LINE':
                extracted_text += block['Text'] + '\n'

        # Initialize Pinecone and OpenAI embeddings
        pinecone.init(api_key=pinecone_api_key, environment=pinecone_environment)
        index = pinecone.Index("smartdocuhub-vectors")
        embeddings = OpenAIEmbeddings(api_key=openai_api_key)

        # Create a document with the extracted text and store it in Pinecone
        doc_id = key.split('.')[0]  # Use the file name as doc_id
        document = Document(page_content=extracted_text, metadata={"doc_id": doc_id})

        vector_store = Pinecone.from_existing_index('smartdocuhub-vectors', embeddings)
        vector_store.add_documents([document])

    return {
        "statusCode": 200,
        "body": json.dumps("Document processed and stored in Pinecone.")
    }
