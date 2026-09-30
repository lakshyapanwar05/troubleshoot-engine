import json
from schema import ContextDeeplinkResponse
from sentence_transformers import SentenceTransformer

d = json.load(open("data/deeplinks.json"))
s = json.load(open("data/siis_responses.json"))
print(len(d["deeplinks"]), len(s["responses"]))
m = SentenceTransformer("models/minilm")
print(m.encode(["screen is blank"]).shape)
print(ContextDeeplinkResponse().model_dump())