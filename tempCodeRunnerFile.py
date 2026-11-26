from agents.code_loader import CodeLoaderAgent
from agents.code_analyzer import CodeAnalyzerAgent


def run_workflow(project_path):

    # Step 1
    loader = CodeLoaderAgent(project_path)
    project_data = loader.load_project()

    # Step 2
    analyzer = CodeAnalyzerAgent(project_data)
    analysis = analyzer.analyze()

    return analysis