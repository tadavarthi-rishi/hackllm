import json
import os
import pinecone
from langchain.embeddings.openai import OpenAIEmbeddings
from langchain.vectorstores import Pinecone
from langchain.chat_models import ChatOpenAI
from langchain.chains.question_answering import load_qa_chain
from botocore.exceptions import ClientError
import boto3

# Initialize AWS Secrets Manager client
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

    # Get query parameters from the API Gateway event
    filename = event['queryStringParameters']['filename']
    query = event['queryStringParameters']['query']
    
    # Create the doc_id from filename
    doc_id = filename.split('.')[0]  # Use the file name as doc_id

    # Initialize Pinecone and OpenAI
    pinecone.init(api_key=pinecone_api_key, environment=pinecone_environment)
    embeddings = OpenAIEmbeddings(api_key=openai_api_key)
    vector_store = Pinecone.from_existing_index('smartdocuhub-vectors', embeddings)

    # Search for the relevant document in Pinecone
    matching_results = vector_store.similarity_search(query, filter={"doc_id": doc_id}, k=2)
    
    if not matching_results:
        return {
            "statusCode": 404,
            "body": json.dumps("Document not found.")
        }

    # Initialize OpenAI for generating responses
    llm = ChatOpenAI(model_name="gpt-4", temperature=0.5, openai_api_key=openai_api_key)
    chain = load_qa_chain(llm, chain_type="stuff")

    # Run the query and generate an answer
    response = chain.run(input_documents=matching_results, question=query)

    return {
        "statusCode": 200,
        "body": json.dumps({"answer": response})
    }
