import json
import boto3
import decimal
import os
import pymysql
from pymysql import Error
from bs4 import BeautifulSoup

class DecimalEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, decimal.Decimal):
            return str(o)
        return super().default(o)

bedrock_runtime = boto3.client("bedrock-runtime")

messages = []

def query_mysql_database(query):

    try:
        connection = pymysql.connect(
            host=os.environ.get('HOST'),
            database=os.environ.get('DB'),
            user=os.environ.get('USER'),
            password=os.environ.get('PASS'),
            cursorclass=pymysql.cursors.DictCursor
        )

        if connection.open:
            with connection.cursor() as cursor:
                cursor.execute(query)
                results = cursor.fetchall()

            return results

    except Error as e:
        print(f"Error: {e}", query)
        return None

    finally:
        if connection.open:
            connection.close()

def get_table_info():
    
    table_infos = []
    tableList = query_mysql_database('SHOW TABLES')
    table_names = [list(table.values())[0] for table in tableList]
    for table_name in table_names:
        table_info = query_mysql_database(f'SHOW CREATE TABLE {table_name}')
        table_infos.append(f"<tableStructure>{table_info[0]['Create Table']}</tableStructure>")
    return '\n\n'.join(table_infos)
    
def call_bedrock(messages):

    response = bedrock_runtime.converse(messages=messages, modelId='anthropic.claude-3-5-sonnet-20240620-v1:0')
    return response["output"]["message"]["content"][0]["text"]
    
def lambda_handler(event, context):
    path = event['requestContext']['http']['path']
    method = event['requestContext']['http']['method']
    
    if path == '/chat' and method.lower() == 'post':
        messages = json.loads(event.get('body'))
        results = None
        
        instructions = "<instructions>Act as an MySQL database expert to write queries. " 
        instructions += "You will be asked to generate MySQL queries based on table structures. "
        instructions += "When you generate a query, ensure it is enclosed in query tag like <query>select * from customers;</query>. "
        instructions += "The query will be used to query a MySQL database so it needs to be valid. No need format the query inside the query tag as it will be sent to a machine. "
        instructions += "User will enclose query question in question tag like <question>give me a list of customers</question>. "
        instructions += "If you don't see the question tag no need to write MySQL query. Just answer the question."
        instructions += f"Here is the structure of the tables:\n\n {get_table_info()}\n\n</instructions>\n\n"
        
        # add instructions to the first message 
        if len(messages) == 1:
            messages[0]['content'][0]['text'] = instructions + messages[0]['content'][0]['text']
            
        output_message = call_bedrock(messages)
        soup = BeautifulSoup(output_message, 'html.parser')
        query = soup.find('query')
        if query:
            query = query.text
            results = query_mysql_database(query)
            
        body = {
            "role": "assistant",
            "content": [
                {"text": output_message}, 
            ],
            'results': results
        }

        return {
            'statusCode': 200, 
            'body': json.dumps(body, cls=DecimalEncoder)  
        }
        
    index = os.path.join(os.path.dirname(__file__), 'index.html')
    with open(index, 'r') as file:
      html_content = file.read()
        
    return {
        'statusCode': 200,
        'headers': {
            'Content-Type': 'text/html',
        },
        'body': html_content 
    }
