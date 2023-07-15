import logging
import os
import requests
import azure.functions as func
import json
import base64
from azure.cosmosdb.table.tableservice import TableService
from azure.cosmosdb.table.models import Entity
from cryptography.fernet import Fernet

def main(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('Python HTTP trigger function processed a request.')
    #errorパラメータがあれば、エラーを表示
    error = req.params.get('error')
    if error:
        return func.HttpResponse(
            f"notionの認証に失敗しました。もう一度お試しください。\n（このページはnotionからリダイレクトされるページです。閉じてもらって大丈夫です）",
            status_code=400
        )
    #codeパラメータがあればcodeを取得
    code = req.params.get('code')
    #stateパラメータがあればstateを取得
    state = req.params.get('state')
    #codeとstateがあれば、改めてnotionにhttpリクエストを送り、データを取得
    if code and state:

        url="https://api.notion.com/v1/oauth/token"
        #クライアントIDとクライアントシークレットを環境変数から取得し、カンマで連結し、base64でエンコード
        encoded_client_id_and_secret = base64.b64encode((os.environ["NOTION_CLIENT_ID"]+":"+os.environ["NOTION_CLIENT_SECRET"]).encode('utf-8'))
        headers = {
            "Content-Type": "application/json",
            "Authorization": "Basic "+encoded_client_id_and_secret.decode('utf-8'),
        }
        body = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": "https://notion-action-register.azurewebsites.net/api/notion-registration-redirect",
        }
        #notionにリクエストを送信
        response = requests.post(url, headers=headers, data=json.dumps(body))
        response_json = response.json()
        
        #レスポンスのduplicated_template_idがnullなら、notionのワークスペースにテンプレートの複製がないということなので、エラーを表示
        message = ""
        if not "duplicated_template_id" in response_json or response_json["duplicated_template_id"] is None:
            message = "notionテンプレートが複製されていません。認証をやり直してください。"
        #stateの値からuser_idを復号する
        f = Fernet(os.environ["DISCORD_USER_ID_ENCRYPT_KEY"])
        user_id = f.decrypt(state.encode('utf-8')).decode('utf-8')
        #DBに登録
        set_notion_info(user_id,response_json)

        return func.HttpResponse(
            #jsonの中身をページに表示
            message+json.dumps(response_json),
            status_code=200
        )



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
             "notionからリダイレクトされて表示されるページ　この文章が出てたらまあリダイレクトは成功（データの保存はしてない）",
             status_code=200
        )

#notionのアクセストークンなどの情報をDBに登録する関数
def set_notion_info(user_id,notion_info):
    try:
        #tokenをDBに登録する
        #DBに登録するためのオブジェクトを作成
        #Azure Table Storageのアカウント名とキー
        storage_account_name = os.environ.get("STORAGE_ACCOUNT_NAME")
        storage_account_key = os.environ.get("STORAGE_ACCOUNT_KEY")
        table_name = "NotionToken"
        #tableserviceオブジェクトを作成
        table_service = TableService(account_name=storage_account_name, account_key=storage_account_key)
        #テーブルがなければ作成
        table_service.create_table(table_name)
        #エンティティを作成
        entity = Entity()
        entity.PartitionKey = "discord"
        entity.RowKey = user_id
        #'dict' object has no attribute 'owner'というエラーが出るので、なにかまちがってる
        entity.notion_user_id = notion_info["owner"]["user"]["id"]
        entity.workspace_name = notion_info["workspace_name"]
        entity.workspace_icon = notion_info["workspace_icon"]
        entity.workspace_id = notion_info["workspace_id"]
        entity.bot_id = notion_info["bot_id"]
        entity.duplicated_template_id = notion_info["duplicated_template_id"]
        #エンティティを登録または置換
        table_service.insert_or_replace_entity(table_name, entity)
        return True
    except Exception as e:
        logging.error(e)
        return False