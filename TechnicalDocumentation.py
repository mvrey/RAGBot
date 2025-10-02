import zipfile
import requests
import frontmatter
from tqdm import tqdm
import TextChunker

class TechnicalDocumentation:
    
    def __init__(self, zip_path: str):
        self.repo_path = zip_path
        self.files_dictionary = []
        self.chunker = TextChunker("")
        self.processed_docs = 0
        self.skipped_docs = 0
    
    
    def get_repo_doc_files(self):
        resp = requests.get(self.zip_path)
        
        if resp.status_code != 200:
            raise Exception(f"Failed to download repository: {resp.status_code}")

        repository_data = []
        zf = zipfile.ZipFile(io.BytesIO(resp.content))
        
        for file_info in zf.infolist():
            filename = file_info.filename
            filename_lower = filename.lower()

            if not (filename_lower.endswith('.md') 
                or filename_lower.endswith('.mdx')):
                continue
        
            try:
                with zf.open(file_info) as f_in:
                    content = f_in.read().decode('utf-8', errors='ignore')
                    post = frontmatter.loads(content)
                    data = post.to_dict()
                    data['filename'] = filename
                    repository_data.append(data)
            except Exception as e:
                print(f"Error processing {filename}: {e}")
                continue
        
        zf.close()
        return repository_data
    

    def chunk_by_characters(self):
        for doc in self.files_dictionary:
            doc_copy = doc.copy()
            if 'content' not in doc_copy:
                self.skipped_docs += 1
                continue
            
            self.processed_docs += 1
            doc_content = doc_copy.pop('content')
            chunks = self.chunker.sliding_window(doc_content, 2000, 1000)
            for chunk in chunks:
                chunk.update(doc_copy)
            self.files_dictionary.extend(chunks)


    def chunk_by_paragraphs(self):
        for doc in self.files_dictionary:
            doc_copy = doc.copy()
            if 'content' not in doc_copy:
                skipped_docs += 1
                continue
            
            processed_docs += 1
            doc_content = doc_copy.pop('content')
            chunks = self.chunker.chunk_by_paragraphs(doc_content)
            self.files_dictionary.extend(chunks)


    def chunk_by_markdown_headings(self, level=2):
        for doc in self.files_dictionary:
            doc_copy = doc.copy()
            if 'content' not in doc_copy:
                skipped_docs += 1
                continue
            
            processed_docs += 1
            doc_content = doc_copy.pop('content')
            chunks = self.chunker.split_markdown_by_level(doc_content, level=2)
            self.files_dictionary.extend(chunks)



    def llm_chunking(self):
        for doc in tqdm(self.files_dictionary):
            doc_copy = doc.copy()
            doc_content = doc_copy.pop('content')

            sections = intelligent_chunking(doc_content)
            for section in sections:
                section_doc = doc_copy.copy()
                section_doc['section'] = section
                self.files_dictionary.append(section_doc)


    def print_summary(self):
        print(f"Processed documents: {self.processed_docs}")
        print(f"Skipped documents: {self.skipped_docs}")
        print(f"Total chunks created: {len(self.files_dictionary)}")