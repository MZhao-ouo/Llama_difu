import os
import llama_index
from llama_index import GPTSimpleVectorIndex, SimpleDirectoryReader
from llama_index import Document, LLMPredictor, PromptHelper, QuestionAnswerPrompt, JSONReader
from langchain.llms import OpenAIChat
from zipfile import ZipFile

from utils import *

def save_index(index, index_name):
    file_path = f"./index/{index_name}.json"
    
    if not os.path.exists(file_path):
        index.save_to_disk(file_path)
        print(f'Saved file "{file_path}".')
    else:
        i = 1
        while True:
            new_file_path = f'{os.path.splitext(file_path)[0]}_{i}{os.path.splitext(file_path)[1]}'
            if not os.path.exists(new_file_path):
                index.save_to_disk(new_file_path)
                print(f'Saved file "{new_file_path}".')
                break
            i += 1

def construct_index(api_key, tmp_file, index_name, max_input_size=4096, num_outputs=512, max_chunk_overlap=20):
    # directory_path = f"./data/{directory_name}"
    documents_set = []
    # for root, dirs, files in os.walk(directory_path):
    #     for file in files:
    #         with open(os.path.join(root, file), 'r', encoding="utf-8") as f:
    #             documents_set.append(f.read())
    # documents = [Document(k) for k in documents_set]
    with open(tmp_file.name, 'r', encoding="utf-8") as f:
        documents_set.append(f.read())
    documents = [Document(k) for k in documents_set]
    
    # Customizing LLM
    llm_predictor = LLMPredictor(llm=OpenAIChat(temperature=0, model_name="gpt-3.5-turbo", openai_api_key=api_key))
    prompt_helper = PromptHelper(max_input_size, num_outputs, max_chunk_overlap)
    
    index = GPTSimpleVectorIndex(documents, llm_predictor=llm_predictor, prompt_helper=prompt_helper)
    
    save_index(index, index_name)

    newlist = refresh_json_list(plain=True)
    return newlist, newlist


def ask_ai(api_key, index_select, question, prompt_tmpl):
    index = load_index(index_select)
    
    prompt = QuestionAnswerPrompt(prompt_tmpl)
    
    llm_predictor = LLMPredictor(llm=OpenAIChat(temperature=0, model_name="gpt-3.5-turbo", openai_api_key=api_key))
    try:
        response = index.query(question, llm_predictor=llm_predictor, similarity_top_k=3, text_qa_template=prompt)
    except Exception as e:
        print(e)
        
    print(f"Response: {response.response}")
    return response.response


def load_index(index_name):
    index_path = f"./index/{index_name}.json"
    if not os.path.exists(index_path):
        return None
    
    index = GPTSimpleVectorIndex.load_from_disk(index_path)
    return index

def display_json(json_select):
    json_path = f"./index/{json_select}.json"
    if not os.path.exists(json_path):
        return None
    documents = JSONReader().load_data(f"./index/{json_select}.json")
    
    return documents[0]
