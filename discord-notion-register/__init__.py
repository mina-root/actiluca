import logging
import os
import azure.functions as func
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.exceptions import InvalidSignature
from cryptography.fernet import Fernet
import json
from azure.cosmosdb.table.tableservice import TableService
from azure.cosmosdb.table.models import Entity
import datetime
import requests
import urllib.parse

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
    #返信用のURLを作成
    url = "https://discord.com/api/v10/interactions/"+interaction["id"]+"/"+interaction["token"]+"/callback"
    #interactionのtypeが2の場合は、slash commandのリクエストである
    if interaction and interaction['type'] == 2: #2: slash command
        embed = None
        component = None
        logging.info('slash command')
        #ここまで
        command = interaction["data"]["name"]
        if command == "settoken":
            user_id = interaction["member"]["user"]["id"]
            token = interaction["data"]["options"][0]["value"]
            username = interaction["member"]["user"]["username"]
            if settoken(username,user_id,token):
                content_text = f"{username}のtokenを登録しました。"
            else:
                content_text = f"{username}のtokenの登録に失敗しました。"
        elif command == "notion-register":
            #notion-registerはnotionとの連携用のリンクを生成する
            user_id = interaction["member"]["user"]["id"]
            url = notion_auth_url(user_id)
            content_text = f"notionとの連携用のリンクを生成しました。以下のリンクボタンからnotionと連携してください。n\n**このリンクはあなたのアカウントに紐づいています。他の人に決して教えないでください！**"
            component = {
                "type": 1, #1: action row https://discord.com/developers/docs/interactions/message-components#action-rows
                "components": [
                    {
                        #notionとの連携用のリンクボタン
                        "type": 2, #2: button https://discord.com/developers/docs/interactions/message-components#buttons
                        "style": 5, #5: link
                        "label": "notionと連携する",
                        "url": url
                    }
                ]
            }
        elif command == "act":
            #actはnotionのデータベースにアクションを登録する
            #まず、tokenを取得する
            user_id = interaction["member"]["user"]["id"]
            token = gettoken(user_id)
            #tokenが登録されていない場合は、tokenを登録するようにメッセージを返す
            if token == None:
                content_text = f"{username}のtokenが登録されていません。tokenを登録してください。"
            else:
                #tokenが登録されている場合は、notionにアクションを登録する
                #アクション名がある場合は、アクション名を取得する
                action_name = ""
                #optionプロパティがある場合は、アクション名を取得する
                if "options" in interaction["data"]:
                    action_name = interaction["data"]["options"][0]["value"]
                #現在時刻を取得
                start_time = datetime.datetime.now().strftime('%Y/%m/%d %H:%M:%S')
                action_active = True

                #notionへの実際の登録処理はまだnotion APIの使い方がわからない
                #返信用のコンポーネントを作成
                #終了ボタンを作成
                component = {
                    "type": 1, #1: action row https://discord.com/developers/docs/interactions/message-components#action-rows
                    "components": [
                        {
                            #終了ボタン
                            "type": 2, #2: button https://discord.com/developers/docs/interactions/message-components#buttons
                            "style": 2, #2: danger
                            "label": "アクションを終了",
                            "custom_id": "end"
                        }
                    ]
                }
                embed = {
                    "title": "新しいアクション",
                    "description": "",
                    "color": 0x0060ff,
                    "fields": [
                        {
                            "name": "アクションの名前",
                            "value": (action_name if action_name != "" else "(未登録)"),
                            "inline": False
                        },
                        {
                            "name": "開始時刻",
                            "value": start_time,
                            "inline": False
                        }
                    ]
                }
                content_text = f"新しいアクションを開始しました。"

        body_data = {
            "type": 4,
            "data": {
                "content": content_text
            }
        }

        if embed:
            body_data["data"]["embeds"] = [embed]

        if component:
            body_data["data"]["components"] = [component]
      
        response = func.HttpResponse(
            status_code=200,
            mimetype="application/json",
            body = json.dumps(body_data) 
            )


        logging.info('response : '+content_text)
        return response
    
    #コンポーネントのアクションの場合
    elif interaction and interaction['type'] == 3: #3: component
        logging.info('component')
        #notionのtokenを取得
        user_id = interaction["member"]["user"]["id"]
        token = gettoken(user_id)
        #コンポーネントのcustom_idを取得
        custom_id = interaction["data"]["custom_id"]
        #custom_idがend（終了ボタン）の場合
        if custom_id == "end":
            #アクションを終了する
            #notionへ登録する情報を入れる入力フォームを作成
            #暫定として入力済みのアクション名と開始時刻をnotionから取得する

            #notionから読みだす（あとでかく）
            action_name = "name_test"
            start_time = "time_test"
            end_time = datetime.datetime.now().strftime('%Y/%m/%d %H:%M:%S')
            body = json.dumps(create_action_form(action_name=action_name,start_time=start_time, end_time=end_time,token=token),ensure_ascii=False)
            logging.info('register form body : '+body)
            response = func.HttpResponse(
                status_code=200,
                mimetype="application/json",
                body = body
                )
            #r = requests.post(url, data=body.encode("utf-8"), headers={'Content-Type': 'application/json'})
            return response


    #pingコマンドの場合
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
    
#discordからのリクエストを検証する関数
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

#tokenをDBに登録する関数
def settoken(user_name,user_id,token):
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
        entity.token = token
        entity.user_name = user_name
        #エンティティを登録または置換
        table_service.insert_or_replace_entity(table_name, entity)
        return True
    except Exception as e:
        logging.error(e)
        return False
    
#IDからtokenを取得する
def gettoken(user_id):
    #Tabel Storageからtokenを取得する
    #Azure Table Storageのアカウント名とキー
    storage_account_name = os.environ.get("STORAGE_ACCOUNT_NAME")
    storage_account_key = os.environ.get("STORAGE_ACCOUNT_KEY")
    table_name = "NotionToken"
    #tableserviceオブジェクトを作成 
    table_service = TableService(account_name=storage_account_name, account_key=storage_account_key)
    #user_idを指定してエンティティを取得(あれば)
    entity = table_service.get_entity(table_name, "discord", user_id)
    #なければNoneを返す
    if not entity:
        return None
    #tokenを返す
    return entity.token

#notionからカテゴリのリストを取得する
#引数はtoken、オプションとしてparent_idを指定できる
def get_category_list(token,parent_id=None):
    #parent_idが指定されていない場合は、rootになっているカテゴリのみを取得する
    if not parent_id:
        pass
    #parent_idが指定されている場合は、そのカテゴリの子カテゴリを取得する
    else:
        pass
    #テスト用のカテゴリのリストを返す
    category_list = [
        {
            "label": "category1",
            "value": "category1",
            "description": "category1の説明"
        },
        {
            "label": "category2",
            "value": "category2",
            "description": "category2の説明"
        },
        {
            "label": "category3",
            "value": "category3",
            "description": "category3の説明"
        }
    ]
    return category_list

#アクション登録用のフォームを作成する
def create_action_form(token,action_name="",start_time="",end_time="",category_list=[],selected_category=None,note=""):
    #discord用もアクション登録用のフォームを作成する
    register_form = {
        "type": 9,
        "data": {
            "title": "アクション登録",
            "custom_id": "action_register_modal",
            "components": [
                {
                    "type": 1, #1: action row https://discord.com/developers/docs/interactions/message-components#action-rows                    
                    "components": [
                        {
                            #アクション名を入力するフォーム
                            "type": 4, #4: input https://discord.com/developers/docs/interactions/message-components#action-rows
                            "custom_id": "action_name_input",
                            "label": "アクション名を入力してください",
                            "placeholder": "ここにアクション名を入力",
                            "value": action_name,
                            "max_length": 100,
                            "min_length": 1,
                            "style": 1, #1: blurple https://discord.com/developers/docs/interactions/message-components#button-object-button-styles
                        }
                        ]
                },{
                    "type": 1, #1: action row https://discord.com/developers/docs/interactions/message-components#action-rows
                    "components": [
                        {
                            #開始時刻を入力するフォーム
                            "type": 4, #4: input https://discord.com/developers/docs/interactions/message-components#action-rows
                            "custom_id": "start_time_input",
                            "label": "開始時刻",
                            "placeholder": "(書式 : yyyy/mm/dd hh:mm:ss)",
                            "value": start_time,
                            "max_length": 30,
                            "style": 1, #1: blurple https://discord.com/developers/docs/interactions/message-components#button-object-button-styles
                        }
                        ]
                },{
                    "type": 1, #1: action row https://discord.com/developers/docs/interactions/message-components#action-rows
                    "components": [
                        {
                            #終了時刻を入力するフォーム
                            "type": 4, #4: select menu https://discord.com/developers/docs/interactions/message-components#select-menus
                            "custom_id": "end_time_input",
                            "label": "終了時刻",
                            "placeholder": "(書式 : yyyy/mm/dd hh:mm:ss)",
                            "value": end_time,
                            "max_length": 30,
                            "style": 1, #1: blurple https://discord.com/developers/docs/interactions/message-components#button-object-button-styles
                        }
                        ]
                },{
                    "type": 1, #1: action row https://discord.com/developers/docs/interactions/message-components#action-rows
                    "components": [
                        {
                            #備考テキストを入力するフォーム
                            "type": 4, #4: input https://discord.com/developers/docs/interactions/message-components#action-rows
                            "custom_id": "note_input",
                            "label": "備考（あれば）",
                            "placeholder": "ここに備考を入力",
                            "max_length": 4000,
                            "min_length": 0,
                            "value": "",
                            "style": 2,
                            "required": False
                        }
                    ]    
                }
            ]
        }
    }

    return register_form

#notionの情報を検索し、ページ名が一致するページのIDを返す
def notion_get_rootpage(token,page_name):
    url=url = f"https://api.notion.com/v1/search"
    headers = json.dumps({
        "accept": "application/json",
        "notion_version": "2022-06-28",
        "Authorization": "Bearer "+token
        })
    payload = json.dumps({
        "query": page_name,
        "filter": {
            "property": "object",
            "value": "page"
        },
        "sort": {
            "direction": "ascending",
            "timestamp": "last_edited_time"
        }
    })
    response = requests.request("POST", url, headers=headers, data=payload)
    reslut = json.loads(response.text)
    #ページが見つかった場合は、ページのIDを返す
    if reslut["results"]:
        return reslut["results"][0]["id"]
    #ページが見つからなかった場合は、Noneを返す
    else:
        return None

#notion認証用のURLを作成する
def notion_auth_url(user_id):
    url_base = "https://api.notion.com/v1/oauth/authorize?client_id=1747a4a7-f6ba-49b0-9258-9a51b8b6e9a5&response_type=code&owner=user&redirect_uri=https%3A%2F%2Fnotion-action-register.azurewebsites.net%2Fapi%2Fnotion-registration-redirect"
    #user_idを暗号化する
    #暗号化するためのキーを取得する
    key = os.environ.get("DISCORD_USER_ID_ENCRYPT_KEY")
    #キーを元にFernetオブジェクトを作成する
    f = Fernet(key)
    #user_idを暗号化する
    user_id_encrypted = f.encrypt(user_id.encode('utf-8')).decode('utf-8')
    url_suffix = urllib.parse.quote(user_id_encrypted)
    #urlに暗号化されたuser_idを追加する
    url = url_base + "&state=" + url_suffix
    return url


