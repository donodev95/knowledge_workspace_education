# import asyncio

# from ollama import AsyncClient
# from pydantic import BaseModel


# class TestResponse(BaseModel):
#     answer: str


# async def main():
#     client = AsyncClient(
#         host="http://localhost:11434",
#         timeout=120,  # Allow time for the model to load.
#     )

#     # Check that the server is reachable.
#     models = await client.list()
#     print("Server connected. Models:", [m.model for m in models.models])

#     # Check async chat and structured JSON output.
#     response = await client.chat(
#         model="qwen3.8:latest",
#         format=TestResponse.model_json_schema(),
#         options={"temperature": 0},
#         messages=[
#             {
#                 "role": "user",
#                 "content": 'Return a JSON object with answer set to "OK".',
#             }
#         ],
#     )

#     result = TestResponse.model_validate_json(
#         response.message.content or ""
#     )
#     assert result.answer == "OK", f"Unexpected response: {result}"

#     print("PASS: AsyncClient chat and JSON validation work.")
#     print(result.model_dump())


# if __name__ == "__main__":
#     asyncio.run(main())

from openai import OpenAI
import dotenv
import os

dotenv.load_dotenv()
KEY = os.getenv("KNOWLEDGE_WORKSPACE_TEST_KEY")

client = OpenAI(
  api_key=KEY
)

response = client.responses.create(
  model="gpt-6-luna",
  input="write a haiku about ai",
  store=True,
)

print(response.output_text);


