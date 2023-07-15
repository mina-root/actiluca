import logging
import os
import azure.functions as func
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.exceptions import InvalidSignature
import json
from azure.cosmosdb.table.tableservice import TableService
from azure.cosmosdb.table.models import Entity

def main(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('Python HTTP trigger function processed a request.')
        
    #証明書を検証し、discordからのリクエストであることを確認する
    #discordからのリクエストでない場合は、401を返す
    #headerからx-signature-ed25519とx-signature-timestampを取得する
    signature = req.headers.get('x-signature-ed25519')
    timestamp = req.headers.get('x-signature-timestamp')
    raw_body = req.get_body().decode('utf-8')
    logging.info('signature : '+signature)
    logging.info('timestamp : '+timestamp)
    if not verify(signature, timestamp, raw_body):
        response = func.HttpResponse("Unauthorized", status_code=401)
        return response
    logging.info('signature verified')
    interaction = json.loads(raw_body)
    logging.info('interaction : '+str(interaction))
    #interactionのtypeが2の場合は、slash commandのリクエストである
    if interaction and interaction['type'] == 2: #2: slash command
        logging.info('slash command')
        #ここまで
        command = interaction["data"]["name"]
        if command == "settoken":
            user_id = interaction["member"]["user"]["id"]
            token = interaction["data"]["options"][0]["options"][0]["value"]
            username = interaction["member"]["user"]["username"]
            if settoken(username,user_id,token):
                content_text = f"{username}のtokenを登録しました。"
            else:
                content_text = f"{username}のtokenの登録に失敗しました。"
        response = func.HttpResponse(
            status_code=200,
            mimetype="application/json",
            body = json.dumps({
                "type":  4, #4: channel message with source https://discord.com/developers/docs/interactions/receiving-and-responding#interaction-response-object-interaction-callback-type
                "data": {
                    "content": content_text
                }
            })
            )
        logging.info('response : '+content_text)
        return response
    else:
        response = func.HttpResponse(
            status_code=200,
            mimetype="application/json",
            body= json.dumps({
                "type": 1 # 1: pong https://discord.com/developers/docs/interactions/receiving-and-responding#interaction-object-interaction-type
            })
        )
        return response

    name = req.params.get('name')
    if not name:
        try:
            req_body = req.get_json()
        except ValueError:
            pass
        else:
            name = req_body.get('name')

    if name:
        return func.HttpResponse(f"Hello, {name}. This HTTP triggered function executed successfully.")
    else:
        return func.HttpResponse(
             "This HTTP triggered function executed successfully. Pass a name in the query string or in the request body for a personalized response.",
             status_code=200
        )

def verify(signature, timestamp, raw_body):
    # Load the public key
    public_key_bytes = bytes.fromhex(os.environ.get("DISCORD_PUBLIC_KEY"))
    public_key = Ed25519PublicKey.from_public_bytes(public_key_bytes)

    try:
        # Verify the signature
        public_key.verify(bytes.fromhex(signature),(timestamp + raw_body).encode('utf-8')) 
        return True
    except InvalidSignature:
        return False

def settoken(user_name,user_id,token):
    try:
        #tokenをDBに登録する
        #DBに登録するためのオブジェクトを作成
        #Azure Table Storageのアカウント名とキー
        storage_account_name = os.environ.get("STORAGE_ACCOUNT_NAME")
        storage_account_key = os.environ.get("StorageConnectionString")
        table_name = "NotionToken"
        #tableserviceオブジェクトを作成
        table_service = TableService(account_name=storage_account_name, account_key=storage_account_key)
        #テーブルがなければ作成
        table_service.create_table(table_name)
        #エンティティを作成
        entity = Entity()
        entity.PartitionKey = "discord"
        entity.RowKey = user_id
        entity.token = token
        entity.user_name = user_name
        #エンティティを登録または置換
        table_service.insert_or_replace_entity(table_name, entity)
        return True
    except Exception as e:
        logging.error(e)
        return False
