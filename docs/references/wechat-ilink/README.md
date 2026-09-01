# WeChat iLink Gateway References

These files are a bounded reference set for the WeChat iLink channel work. They
are copies of upstream source files and protocol notes, kept here so design and
implementation reviews do not need to load an entire external repository.

## Hermes

- `hermes/base.py` — [BasePlatformAdapter](https://github.com/NousResearch/hermes-agent/blob/1f99a4b2f2982fbef06df00ad673ade4e1895668/gateway/platforms/base.py)
- `hermes/delivery.py` — [delivery.py](https://github.com/NousResearch/hermes-agent/blob/1f99a4b2f2982fbef06df00ad673ade4e1895668/gateway/delivery.py)
- `hermes/stream_dispatch.py` — [stream_dispatch.py](https://github.com/NousResearch/hermes-agent/blob/1f99a4b2f2982fbef06df00ad673ade4e1895668/gateway/stream_dispatch.py)
- `hermes/weixin-tutorial.py` — [tutorial Weixin adapter](https://github.com/az9713/hermes-agent-tutorial/blob/babc17a066858fa8d32e1152a9e202ce523c1f74/gateway/platforms/weixin.py)

## wechatbot

The three files below are copied from the local checkout at
`/Users/seanlee/DevelopCode/MoreAlpha/wechatbot`, whose `main` HEAD was
`6914de4e4cae966b1a3f4c6531711c9dffd84fee` when this reference set was made.

- `wechatbot/protocol.md` — protocol reference
- `wechatbot/client.py` — high-level client, context and typing lifecycle
- `wechatbot/protocol.py` — endpoint and wire message implementation

The local project notes in `/Users/seanlee/DevelopCode/MoreAlpha/protocol-spec.md`
remain the explanatory source for observed protocol behavior and operational
recommendations.
