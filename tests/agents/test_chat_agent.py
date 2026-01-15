from agents import chat_agent_factory

agent = chat_agent_factory()
while True:
    question = input("问题：")
    response = agent.step(question)

    for chunk_response in response:
        message = chunk_response.msgs[0]
        content_text = message.content
        if content_text:
            print(content_text, end="", flush=True)
    print("\n")
    print("-"*100)
    print(agent.memory.get_context())
    print("-" * 100)


