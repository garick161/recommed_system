# -*- coding: utf-8 -*-
"""get_distilbet_emdedding.ipynb

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/1xpzgPtCcbKpoVAYBu0pVqBRArrdAO-CF
"""

import pandas as pd
import torch
import torch.nn as nn
from torch.utils.data import DataLoader
from datasets import Dataset
import pyarrow as pa
import pyarrow.dataset as ds

from tqdm import tqdm
from warnings import filterwarnings
filterwarnings('ignore')


@torch.inference_mode()
def get_embeddings(model, loader):

    device = torch.device('cuda:0' if torch.cuda.is_available() else 'cpu')
    torch.cuda.empty_cache()
    model = model.to(device)
    model.eval()

    total_embeddings = []
    idx_list = []

    for batch in tqdm(loader):
        idx_list.append(batch['index'].unsqueeze(1))
        batch = {key: batch[key].to(device) for key in ['attention_mask', 'input_ids']}
        embeddings = model(**batch)['last_hidden_state'][:, 0, :]
        total_embeddings.append(embeddings.cpu())

    return torch.cat(total_embeddings, dim=0), torch.cat(idx_list, dim=0).to(torch.int64)

def text2emb_simple(df: pd.DataFrame, text_col_name: str): # -> pd.DataFrame
    """Функция преобразования текстов в датафрейме в эмбеддинги с помощью DistilBertModel

    Parameters
    ----------
    df: pd.DataFrame с признаками

    text_col_name: str

        Имя колонки, для которой нужно получить эмбеддинги

    Returns
    -------
    final_df : pd.DataFrame

        Датафрейм с исходными признаками + 768 колонок с вещественными
        значениями(векторное представление текста размерностью 768)
    """

    def get_pyarrow(df): # convert to Huggingface dataset

        dataset = ds.dataset(pa.Table.from_pandas(df).to_batches())

        return Dataset(pa.Table.from_pandas(df))


    def tokenization_text(example):
        return tokenizer.batch_encode_plus(example[text_col_name], add_special_tokens=True,
                                       return_token_type_ids=False, truncation=True)


    tokenizer = AutoTokenizer.from_pretrained('distilbert-base-cased')
    model = DistilBertModel.from_pretrained('distilbert-base-cased')

    # Подготовка данных для передачи в модель
    df = df.copy().reset_index()
    text_df = df[['index', text_col_name]]

    text_dataset = get_pyarrow(text_df)

    text_dataset = text_dataset.map(tokenization_text, batched=True)

    text_dataset.set_format(type="torch", columns=["input_ids", "attention_mask", 'index'])

    data_collator = DataCollatorWithPadding(tokenizer=tokenizer)
    text_loader = DataLoader(text_dataset, batch_size=32,
                             collate_fn=data_collator, pin_memory=True, shuffle=False)

    # Получение эмбеддингов
    embeddings_text, idx_text = get_embeddings(model, text_loader)

    # Собирание итогового df
    text_df = pd.DataFrame(np.concatenate((embeddings_text.numpy(), idx_text.numpy()), axis=1))


    text_df = text_df.add_prefix('text_')
    text_df = text_df.rename(columns={text_df.columns[-1]: 'index'})

    text_df['index'] = text_df['index'].astype(int)

    final_df = pd.merge(df, text_df, on='index')

    return final_df