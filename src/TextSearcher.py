from tqdm import tqdm
from sentence_transformers import SentenceTransformer
from minsearch import VectorSearch
import numpy as np
from index import Index


class TextSearcher:
    
    def __init__(self):
        pass

    def text_search(self, query, dtc_fastapi):
        index = Index(
        text_fields=["chunk", "title", "description", "filename"],
        keyword_fields=[]
        )

        index.fit(dtc_fastapi)
        return index.search(query, num_results=2)


    def vector_search(self, query, dtc_fastapi):
        embedding_model = SentenceTransformer('multi-qa-distilbert-cos-v1')
        faq_embeddings = []
        print(f"Encoding text:\n")

        for d in tqdm(dtc_fastapi):
            if 'content' not in d:
                text = ''
            else:
                #TODO: replace the question with a set of possible questions that ought to be asked about about the docs. Let the llm suggest some possible questions.
                text = '''question +''' ' ' + d['content']
            v = embedding_model.encode(text)
            faq_embeddings.append(v)

        faq_embeddings = np.array(faq_embeddings)

        faq_vindex = VectorSearch()
        faq_vindex.fit(faq_embeddings, dtc_fastapi)

        q = embedding_model.encode(query)
        


    def hybrid_search(self, query, dtc_fastapi):
        text_results = self.text_search(query, dtc_fastapi)
        vector_results = self.vector_search(query, dtc_fastapi)
        
        # Combine and deduplicate results
        seen_ids = set()
        combined_results = []

        for result in text_results + vector_results:
            print(result)
            if result['chunk'] not in seen_ids:
                seen_ids.add(result['chunk'])
                combined_results.append(result)
        
        return combined_results