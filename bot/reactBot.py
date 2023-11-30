import json
from flask import Flask, request, make_response
from slackBot import SlackBot
from recommendBot import OutputRestaurant, Recommendation
from gspreadFinder import get_spreadsheet_data
import os
from dotenv import load_dotenv
import re
import random

load_dotenv()

slack_token = os.getenv("SLACK_OAUTH_TOKEN")
myBot = SlackBot(slack_token)
app = Flask(__name__)

SERVICE_ACCOUNT_FILE = '../splendid-myth-353301-a63d721b9519.json'
SPREADSHEET_ID = os.getenv("GOOGLE_SHEET_ID")
RANGE_NAME = '시트1!A2:G30'

class SlackEventHandler:
    def __init__(self, bot):
        self.bot = bot
        self.greeting = ["안녕", "하이", "방가"]
        self.member = ["병룡님", "민협님", "영롱님", 
                       "원상님", "찬규님", "현지님", 
                       "찬욱님", "석희님", "민우님", 
                       "현준님", "예진님", "종민님", 
                       "소현님", "무룡님", "윤선님", 
                       "종찬님", "호윤님", "지용님", 
                       "형준님", "주광님"]
        
        self.message_dict = {
            'how_to_use': 
                """
                    안녕하세요! 커널 360봇 입니다!
                    멘션해주셔서 감사합니다.
                    업데이트 및 관련 요청 문의는 석희님 원상님 현준님을 멘션해주세요.
               """
            ,
            'greeting': "안녕하세요~! 반갑습니다 커널 봇입니다.",
        }

    def _get_event_details(self, slack_event):
        
        channel = slack_event["event"]["channel"]
        message_ts = slack_event["event"]["event_ts"]
        return channel, message_ts


    def send_message(self, event_type, slack_event, message_type):
        
        channel, message_ts = self._get_event_details(slack_event)
        self.bot.post_message(channel, self.message_dict.get(message_type, "메세지타입이 확인되지 않았습니다."))
        return make_response(f"{event_type} 이벤트 핸들러를 찾을 수 없습니다.", 200, {"X-Slack-No-Retry": 1})


    def random_member(self, event_type, slack_event, num):
        
        channel, message_ts = self._get_event_details(slack_event)

        selected_members = random.sample(self.member, min(int(num), len(self.member)))
        text = ', '.join(selected_members)
        self.bot.post_message(channel, text)

        return make_response(f"{event_type} 이벤트 핸들러를 찾을 수 없습니다." , 200, {"X-Slack-No-Retry": 1})
    
    
    def _parse_distance(self, category_lower):
        if "km" in category_lower:
            return float(category_lower.replace("km", ""))
        elif "m" in category_lower:
            return float(category_lower.replace("m", "")) / 1000
        return None
    
    
    def random_restaurant(self, event_type, slack_event, category, count):
        values = get_spreadsheet_data(SERVICE_ACCOUNT_FILE, SPREADSHEET_ID, RANGE_NAME)
        recommendation = Recommendation(values)
        
        distance = self._parse_distance(category.lower())
        
        restaurant_methods = {
            'distance': lambda: recommendation.get_close_restaurant(distance, int(count)),
            '무작위': lambda: recommendation.get_random(int(count)),
            'default': lambda: recommendation.get_categorized_restaurant(category, int(count))
        }

        method = restaurant_methods.get('distance' if distance is not None else category.lower(), restaurant_methods['default'])
        restaurants = method()

        text = "\n".join([OutputRestaurant(row.tolist()).__str__() for _, row in restaurants.iterrows()])

        channel, _ = self._get_event_details(slack_event)

        if text:
            self.bot.post_message(channel, text)
        else:
            message = f"[{category}] 적절한 카테고리가 없습니다."
            self.bot.post_message(channel, message)

        return make_response(message, 200, {"X-Slack-No-Retry": 1})


    @staticmethod
    def catch_restaurant(text):
        pattern = r"식당추천\s+(\S+)\s+(\d+)군데"
        match = re.search(pattern, text)

        if match:
            category = match.group(1)
            count = int(match.group(2))
            return category, count
        else:
            return None,None


    def sendQr(self, slack_event):
        
        channel = slack_event["event"]["channel"]
        message = slack_event["event"]["event_ts"]
        self.bot.post_qr_image(channel)
        return make_response(message, 200, {"X-Slack-No-Retry": 1})


    def handle_app_mention(self, text, event_type, slack_event):
        
        if "식당추천" in text:
            category, count = self.catch_restaurant(text)
            return self.random_restaurant(event_type, slack_event, category, count)
        if re.search(r"추첨\s+\d+", text):
            num = re.search(r"추첨\s+(\d+)", text).group(1)
            return self.random_member(event_type, slack_event, num)
        if "qr" in text:
            return self.send_qr(slack_event)
        if any(greeting in text for greeting in self.greeting):
            return self.say_hello(event_type, slack_event)
        return self.show_how_to_use(event_type, slack_event)


    def event_handler(self, event_type, slack_event):
        
        print(slack_event)
        if event_type == "app_mention":
            return self.handle_app_mention(slack_event["event"]["text"], event_type, slack_event)

        response_text = f"안녕하세요. 스레드 봇이 알 수 없는 요청입니다 github에 issue report를 남겨주세요"
        channel, _ = self._get_event_details(slack_event)
        self.bot.post_message_in_thread(channel, slack_event["event"]["event_ts"], response_text)
        return make_response(response_text, 200, {"X-Slack-No-Retry": 1})
    
    
@app.route("/slack", methods=["GET", "POST"])
def hears():
    slack_event = json.loads(request.data)
    if "challenge" in slack_event:
        print (slack_event["challenge"])
        response_dict = {"challenge": slack_event["challenge"]}
        return response_dict
    
    if "event" in slack_event:
        event_type = slack_event["event"]["type"]
        slack_event_handler = SlackEventHandler(myBot)
        return slack_event_handler.event_handler(event_type, slack_event)
    
    return make_response("슬랙 요청에 이벤트가 없습니다.", 404, {"X-Slack-No-Retry": 1})

if __name__ == '__main__':
    app.run('0.0.0.0', port=8080)
