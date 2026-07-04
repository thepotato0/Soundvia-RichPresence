import discordrpc
import logging
import time
import sys

logger = logging.getLogger(__name__.replace("_",""))
APPID="1522642631472185465"

class App:
    def __init__(self,logging_level:int=logging.INFO,app_id:str=APPID):
        self.app_id = app_id 
        self.setup_logging(logging_level)
        logger.info("App started")
        try:
            self.start_discord_presence()
        except discordrpc.exceptions.DiscordNotOpened:
            logger.critical("could not find Discord. is Discord running? exiting in 3 seconds.")
            self.shutdown()
        except Exception:
            logger.exception("Unexpected error while starting Discord presence.")
            self.shutdown()

    def setup_logging(self, logging_level):
        logger.setLevel(logging_level)
        logger.propagate = False  # stop double-printing through root (discordrpc's basicConfig adds a root handler on import)

        if not logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            ))
            logger.addHandler(handler)
        else:
            handler = logger.handlers[0]

        # discordrpc's internal logger is hardcoded to this exact name in its source
        discord_log = logging.getLogger("Discord RPC")
        discord_log.setLevel(logging_level)
        discord_log.propagate = False
        if not discord_log.handlers:
            discord_log.addHandler(handler)  # reuse the same handler so formatting matches
    
    def start_discord_presence(self):
        rpc = discordrpc.RPC(app_id=self.app_id)
        rpc.set_activity(
            details="Music",
            state="by Music artist",
            act_type=discordrpc.Activity.Listening
        )
        rpc.run()

        
    def shutdown(self,wait_seconds:int=3,status_code:int=1):
        time.sleep(wait_seconds)
        sys.exit(status_code)


if __name__ == "__main__":
    app = App()