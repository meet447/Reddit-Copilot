import praw
from requests import Session
from praw.exceptions import RedditAPIException
from llm.main import create_response
from config import Config, Botconfig
import random
from modules.sleep.main import goto_sleep
from modules.logging.main import write_log

class RedditBot:
    def __init__(self, account, proxy=None) -> None:
        self.username = account['username']
        self.password = account['password']
        self.client_id = account['client_id']
        self.client_secret = account['client_secret']
        self.proxy = proxy
        self.session = Session()

        # Configure proxy if provided
        if proxy:
            self.configure_proxy(self.session, proxy)

        self.reddit = praw.Reddit(
            client_id=self.client_id,
            client_secret=self.client_secret,
            username=self.username,
            password=self.password,
            user_agent=UserAgent().random,
            requestor_kwargs={"session": self.session}
        )
        self.log_file = Botconfig.log_file or "commented_posts.txt"

    def configure_proxy(self, session, proxy):
        proxy_parts = proxy.split(':')
        if len(proxy_parts) == 4:
            ip, port, proxy_username, proxy_password = proxy_parts
            proxy_url = f"http://{proxy_username}:{proxy_password}@{ip}:{port}"
            session.proxies['http'] = proxy_url
            session.proxies['https'] = proxy_url
            print("[Using proxy:] - ", proxy_url)
        else:
            print("[PROXY] - Proxy format is incorrect. Expected format is 'ip:port:username:password'")

    def login(self) -> bool:
        try:
            print(f"[LOGIN] - Attempting login for {self.username}")
            print(f"[LOGIN] - Logged in as {self.reddit.user.me()}")
            write_log(f"[LOGIN] - Logged in as {self.reddit.user.me()}")
            return True
        except Exception as e:
            print(f"[LOGIN] - Failed to log in: {e}")
            write_log(f"[LOGIN] - Failed to log in: {e}")
            return False

    def get_trending_topics(self) -> list:
        trending_topics = []
        commented_posts = self.load_commented_posts()

        if not Botconfig.new_posts:
            for submission in self.reddit.subreddit("all").hot(limit=500):
                if submission.id not in commented_posts:
                    trending_topics.append(submission)
        else:
            for submission in self.reddit.subreddit("all").new(limit=500):
                if submission.id not in commented_posts:
                    trending_topics.append(submission)

        return trending_topics

    def extract_text_title(self, submission) -> str:
        return submission.title

    def extract_text_content(self, submission) -> str:
        return submission.selftext

    def extract_comment_content_and_upvotes(self, submission) -> list:
        submission.comments.replace_more(limit=0)
        comments = submission.comments.list()
        return [(comment.body, comment.score) for comment in comments]

    def generate_comment(self, submission, title, post_text, comments) -> None:
        comments = sorted(comments, key=lambda comment: comment[1], reverse=True)[:4]
        comments = ", ".join([comment[0] for comment in comments])

        prompt = f'''
        [SYSTEM] You are an avid Reddit user skilled at crafting concise and engaging comments that resonate with the community. Create a comment that aligns with the post titled "{title}" and its top comments: "{comments}".
        '''

        new_prompt = str(prompt)

        if Botconfig.type == "ai":
            comment = create_response(post=new_prompt)
        else:
            comment = random.choice(Botconfig.ads)

        while True:
            try:
                submission.reply(comment)
                print("[SUCCESS] - replied to the post!")
                write_log("[SUCCESS] - replied to the post")
                break
            except RedditAPIException as e:
                if e.error_type == "RATELIMIT":
                    print("[RATE LIMIT] - Rate limited. Sleeping.")
                    write_log("[RATE LIMIT] - Rate limited. Sleeping.")
                    break
                elif e.error_type == "THREAD_LOCKED":
                    print("Thread locked. Skipping.")
                    write_log("Thread locked. Skipping.")
                    break
                else:
                    print(e.error_type)
                    write_log(e.error_type)
                    break

        print(f"[Replied to] - {submission.title} with {comment}")
        write_log(f"[Replied to] - {submission.title} with {comment}")
        self.log_commented_post(submission.id)

    def load_commented_posts(self) -> list:
        try:
            with open(self.log_file, "r") as f:
                return f.read().splitlines()
        except FileNotFoundError:
            return []

    def log_commented_post(self, post_id: str) -> None:
        with open(self.log_file, "a") as f:
            f.write(post_id + "\n")

def get_working_proxy(account):
    for _ in range(len(Botconfig.proxies)):
        proxy = random.choice(Botconfig.proxies)
        bot = RedditBot(account, proxy=proxy)
        if bot.login():
            return proxy
    return None  # If no proxies work

def main():
    # Retrieve trending topics once
    reddit_instance = RedditBot(Config.accounts[0])  # Initializing for subreddit access
    trending_topics = reddit_instance.get_trending_topics()

    for submission in trending_topics:
        print(f"[PROCESSING POST] - '{submission.title}'")
        write_log(f"[PROCESSING POST] - '{submission.title}'")

        # Process the single post for all accounts
        for account in Config.accounts:
            proxy = get_working_proxy(account)

            # Initialize RedditBot with or without proxy based on availability
            if proxy is None:
                print("[PROXY] - All proxies failed. Trying without proxy.")
                reddit_bot = RedditBot(account)
            else:
                reddit_bot = RedditBot(account, proxy=proxy)

            # Attempt to log in and comment with the account
            if reddit_bot.login():
                reddit_bot.generate_comment(submission, 
                                            reddit_bot.extract_text_title(submission),
                                            reddit_bot.extract_text_content(submission),
                                            reddit_bot.extract_comment_content_and_upvotes(submission))
                print(f"[ACCOUNT COMPLETE] - Commented on post '{submission.title}' with account {account['username']}")
                write_log(f"[ACCOUNT COMPLETE] - Commented on post '{submission.title}' with account {account['username']}")
            else:
                print(f"[LOGIN FAILED] - Skipping account {account['username']} due to login failure.")
                write_log(f"[LOGIN FAILED] - Skipping account {account['username']} due to login failure.")

        # Sleep after all accounts have commented on the current post
        print(f"[SLEEP] - Sleeping for {Botconfig.cooldown} seconds before moving to the next post.")
        write_log(f"[SLEEP] - Sleeping for {Botconfig.cooldown} seconds before moving to the next post.")
        
        goto_sleep(Botconfig.cooldown)

if __name__ == "__main__":
    main()
