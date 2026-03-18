from camel.agents.chat_agent import ChatAgent
from camel.messages.base import BaseMessage
from backend.app.core.model_runtime import backend_model, stream_model

stream = True


def agent_factory():
    system_message = '''
        你是一个聊天助手。随便聊天。
        '''

    if stream:
        return ChatAgent(
            system_message=BaseMessage.make_assistant_message(
                role_name="Chat Agent Assistant",
                content=system_message,
            ),
            model=stream_model(),
            stream_accumulate=False
        )
    else:
        return ChatAgent(
            system_message=BaseMessage.make_assistant_message(
                role_name="Chat Agent Assistant",
                content=system_message,
            ),
            model=backend_model(),
        )


agent = agent_factory()
while True:
    question = input("问题：")
    response = agent.step(question)
    if not stream:
        print(response.msg.content)
    else:
        for chunk_response in response:
            message = chunk_response.msgs[0]
            content_text = message.content
            if content_text:
                print(content_text, end="", flush=True)
        print("\n")
        print("-"*100)
        print(agent.memory.get_context())
        print("-" * 100)
    # agent.memory.clear()
