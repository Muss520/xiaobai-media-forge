"""Deterministic-testable companion scheduling, independent of media parameters."""
import random

IDLE_ACTIONS={'idle':3,'tail':3,'look':2,'stretch':1,'sleep':1,
              'wash':2,'lick':2,'scratch':1,'sniff':2,'ears':2,'yawn':1,'lie':1,'hug':2}
IDLE_INTERVALS={'quiet':(20,40),'standard':(10,25),'lively':(5,15)}
ACTION_LABELS={'idle':'眨眨眼','tail':'摇尾巴','look':'看看四周','stretch':'伸个懒腰','sleep':'打个盹',
    'wash':'洗脸','lick':'舔爪','scratch':'挠耳朵','sniff':'闻一闻','ears':'抖耳朵','yawn':'打哈欠',
    'lie':'趴一会','hug':'抱尾巴','pet':'摸摸头','rub':'蹭蹭手','snack':'喂零食','joy':'开心小跳','shy':'害羞',
    'pounce':'扑抓','catch':'接球','meow':'叫一声'}


class IdleScheduler:
    def __init__(self,rng=None):self.rng=rng or random.Random();self.previous=None

    def next(self,activity='standard'):
        choices=[name for name in IDLE_ACTIONS if name!=self.previous]
        action=self.rng.choices(choices,weights=[IDLE_ACTIONS[name] for name in choices])[0]
        self.previous=action;low,high=IDLE_INTERVALS.get(activity,IDLE_INTERVALS['standard'])
        return action,self.rng.randint(low,high)
