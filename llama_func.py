import os
from llama_index import GPTSimpleVectorIndex, GPTTreeIndex, GPTKeywordTableIndex, GPTListIndex
from llama_index import SimpleDirectoryReader, download_loader
from llama_index import Document, LLMPredictor, PromptHelper, QuestionAnswerPrompt, RefinePrompt
from langchain.llms import OpenAIChat, OpenAI
from googlesearch import search as google_search
from baidusearch.baidusearch import search as baidu_search

from utils import *

import logging
import sys

logging.basicConfig(stream=sys.stdout, level=logging.INFO)
logging.getLogger().addHandler(logging.StreamHandler(stream=sys.stdout))

def get_documents(file_src):
    documents = []
    for file in file_src:
        if os.path.splitext(file.name)[1] == '.pdf':
            CJKPDFReader = download_loader("CJKPDFReader")
            loader = CJKPDFReader()
            documents += loader.load_data(file=file.name)
        elif os.path.splitext(file.name)[1] == '.docx':
            DocxReader = download_loader("DocxReader")
            loader = DocxReader()
            documents += loader.load_data(file=file.name)
        elif os.path.splitext(file.name)[1] == '.epub':
            EpubReader = download_loader("EpubReader")
            loader = EpubReader()
            documents += loader.load_data(file=file.name)
        elif "http" in file:
            BeautifulSoupWebReader = download_loader("BeautifulSoupWebReader")
            loader = BeautifulSoupWebReader()
            documents += loader.load_data(file)
        else:
            with open(file.name, 'r', encoding="utf-8") as f:
                text = add_space(f.read())
                documents += [Document(text)]
    return documents

def construct_index(api_key, file_src, index_name, index_type,
                                    max_input_size=4096, 
                                    num_outputs=512, 
                                    max_chunk_overlap=20, 
                                    chunk_size_limit=None,
                                    embedding_limit=None,
                                    separator=" ",
                                    num_children=10,
                                    max_keywords_per_chunk=10):
    
    chunk_size_limit = None if chunk_size_limit == 0 else chunk_size_limit
    embedding_limit = None if embedding_limit == 0 else embedding_limit
    separator = " " if separator == "" else separator
    
    llm_predictor = LLMPredictor(llm=OpenAI(model_name="gpt-3.5-turbo-0301", openai_api_key=api_key))
    prompt_helper = PromptHelper(max_input_size, num_outputs, max_chunk_overlap, embedding_limit, chunk_size_limit, separator=separator)
    documents = get_documents(file_src)
    
    try:
        if index_type == "GPTSimpleVectorIndex":
            index = GPTSimpleVectorIndex(documents, llm_predictor=llm_predictor, prompt_helper=prompt_helper)
            index_name += "_GPTSimpleVectorIndex"
        elif index_type == "GPTTreeIndex":
            index = GPTTreeIndex(documents, llm_predictor=llm_predictor, prompt_helper=prompt_helper, num_children=num_children)
            index_name += "_GPTTreeIndex"
        elif index_type == "GPTKeywordTableIndex":
            index = GPTKeywordTableIndex(documents, llm_predictor=llm_predictor, prompt_helper=prompt_helper, max_keywords_per_chunk=max_keywords_per_chunk)
            index_name += "_GPTKeywordTableIndex"
        elif index_type == "GPTListIndex":
            index = GPTListIndex(documents, llm_predictor=llm_predictor, prompt_helper=prompt_helper)
            index_name += "_GPTListIndex"
    except Exception as e:
        print(e)
        return None
    
    save_index(index, index_name)
    newlist = refresh_json_list(plain=True)
    return gr.Dropdown.update(choices=newlist, value=index_name)

def chat_ai(api_key, index_select, question, prompt_tmpl, refine_tmpl ,sim_k, chat_tone ,context, chatbot, search_mode=[]):
    if index_select == "请选择索引文件":
        chatbot.append((question, "❗请选择索引文件"))
        return context, chatbot
    
    os.environ["OPENAI_API_KEY"] = api_key
    
    print(f"Question: {question}")

    temprature = 2 if chat_tone == 0 else 1 if chat_tone == 1 else 0.5
    index_select = search_construct(api_key, question, search_mode, index_select) if search_mode else index_select
        
    response = ask_ai(api_key, index_select, question, prompt_tmpl, refine_tmpl, sim_k, temprature, context)
    if response is None:
        chatbot.append((question, "查询失败，请换个问法试试"))
        return context, chatbot
    response = parse_text(response)
    
    context.append({"role": "user", "content": question})
    context.append({"role": "assistant", "content": response})
    chatbot.append((question, response))
    
    os.environ["OPENAI_API_KEY"] = ""
    return context, chatbot


def ask_ai(api_key, index_select, question,
           prompt_tmpl,
           refine_tmpl,
           sim_k=1,
           temprature=0,
           prefix_messages=[]):
    os.environ["OPENAI_API_KEY"] = api_key
    # 判断索引文件是否存在
    index_path = f"./index/{index_select}.json"
    if not os.path.exists(index_path):
        return None
        
    llm_predictor = LLMPredictor(llm=OpenAI(temperature=temprature, model_name="gpt-3.5-turbo-0301", prefix_messages=prefix_messages))
    
    if "GPTSimpleVectorIndex" in index_select:
        index = GPTSimpleVectorIndex.load_from_disk(index_path)
        qa_prompt = QuestionAnswerPrompt(prompt_tmpl)
        rf_prompt = RefinePrompt(refine_tmpl)
        response = index.query(question, llm_predictor=llm_predictor, similarity_top_k=sim_k, text_qa_template=qa_prompt, refine_template=rf_prompt)
    elif "GPTTreeIndex" in index_select:
        index = GPTTreeIndex.load_from_disk(index_path)
        response = index.query(question, llm_predictor=llm_predictor)
    elif "GPTKeywordTableIndex" in index_select:
        index = GPTKeywordTableIndex.load_from_disk(index_path)
        response = index.query(question, llm_predictor=llm_predictor)
    elif "GPTListIndex" in index_select:
        index = GPTListIndex.load_from_disk(index_path)
        qa_prompt = QuestionAnswerPrompt(prompt_tmpl)
        response = index.query(question, llm_predictor=llm_predictor)

    print(f"Response: {response.response}")
    
    os.environ["OPENAI_API_KEY"] = ""
    return response.response


def search_construct(api_key, question, search_mode, index_select):
    print(f"You asked: {question}")
    chat = OpenAI(model_name="gpt-3.5-turbo-0301", openai_api_key=api_key)
    search_terms = chat.generate([f"Please extract search terms from the user’s question. The search terms is a concise sentence, which will be searched on Google to obtain relevant information to answer the user’s question, too generalized search terms doesn’t help. Please provide no more than two search terms. Please provide the most relevant search terms only, the search terms should directly correspond to the user’s question. Please separate different search items with commas, with no quote marks. The user’s question is: {question}"]).generations[0][0].text.strip()
    search_terms = search_terms.replace('"', '')
    search_terms = search_terms.replace(".", "")
    links = []
    for keywords in search_terms.split(","):
        keywords = keywords.strip()
        for search_engine in search_mode:
            if "Google" in search_engine:
                print(f"Googling: {keywords}")
                search_iter = google_search(keywords, num_results=5)
                links += [next(search_iter) for _ in range(10)]
            if "Baidu" in search_engine:
                print(f"Baiduing: {keywords}")
                search_results = baidu_search(keywords, num_results=5)
                links += [i["url"] for i in search_results if i["url"].startswith("http") and (not "@" in i["url"])]
            if "Manual" in search_engine:
                print(f"Searching manually: {keywords}")
                print("Please input links manually. (Enter 'q' to quit.)")
                while True:
                    link = input("请手动输入一个链接：\n")
                    if link == "q":
                        break
                    else:
                        links.append(link)
    links = list(set(links))
    if len(links) == 0:
        return index_select
    print("Extracting data from links...")
    print('\n'.join(links))
    search_index_name = " ".join(search_terms.split(","))
    construct_index(api_key, links, search_index_name)
    return search_index_name
