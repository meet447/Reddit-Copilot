import random

# Configure multiple Reddit accounts
class Config:
    accounts = [
        {
            "client_id": "",
            "client_secret": "",
            "username": "jim.w1234@icloud.com",
            "password": "",
        }
    ]

class Botconfig:
    proxies = [
        '38.154.227.167:5868:olzpjyuy:ekl53b9x59d2',
        '92.113.242.158:6742:olzpjyuy:ekl53b9x59d2',
        '23.95.150.145:6114:olzpjyuy:ekl53b9x59d2',
        '198.23.239.134:6540:olzpjyuy:ekl53b9x59d2',
        '207.244.217.165:6712:olzpjyuy:ekl53b9x59d2',
        '107.172.163.27:6543:olzpjyuy:ekl53b9x59d2',
        '216.10.27.159:6837:olzpjyuy:ekl53b9x59d2',
        '136.0.207.84:6661:olzpjyuy:ekl53b9x59d2',
        '142.147.128.93:6593:olzpjyuy:ekl53b9x59d2',
        '206.41.172.74:6634:olzpjyuy:ekl53b9x59d2'
    ]
    
    new_posts = False
    
    # Interval between posts or comments in minutes
    cooldown = 10 
    
    # Set to True if you need to setup webhook for logs
    webhook = ""
    
    discord_webhook = False
     
    # Select purpose of bot: 'ai', 'ad', or 'post'
    type = "ai"
    
    all_subreddits = True
    
    ads = [
        '''
        Advertisement 1: Type what u want to advertise here the exact same message will be commented on random posts!
        ''',
        '''
        Advertisement 2: Another ad message here!
        ''',
        '''
        Advertisement 3: Yet another ad message here!
        ''',
    ]
    
    # If set to False, will only post in the specific subreddits
    subreddits = [
        "AskReddit",
        "funny",
        "gaming",
        "aww",
        "Music",
        "movies",
        "todayilearned",
        "pics",
        "science",
        "worldnews",
        "technology",
        "interestingasfuck",
        "askscience",
        "dataisbeautiful",
        "explainlikeimfive"
    ]

    posts = [
        {"title": "Hey there, upvote for an upvote!", "body": "UPVOTE PLEASE"},
        {"title": "Upvote for upvote, part 2!", "body": "UPVOTE PLEASE"}
    ]
    
    log_file = "commented_posts.txt"

    @staticmethod
    def get_random_proxy():
        if Botconfig.proxies:
            return random.choice(Botconfig.proxies)
        return None
