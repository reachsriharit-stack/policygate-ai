.PHONY: install-locked test compile submission-check demo-pass demo-block ui

install-locked:
	python -m pip install -r requirements.lock

test:
	python -m unittest discover -s tests -v

compile:
	python -m compileall policygate

submission-check: test compile
	@python -c "from pathlib import Path; g=Path('.gitignore').read_text(); required=['.env','terraform/','*.tfstate','*.tfplan']; missing=[x for x in required if x not in g]; assert not missing, f'Missing .gitignore protections: {missing}'; print('Submission hygiene checks passed.')"

demo-pass:
	python -m policygate.app examples/approve_request.txt --approver-name "Jane Smith" --approver-email "jane@example.com"

demo-block:
	python -m policygate.app examples/reject_request.txt --approver-name "Jane Smith" --approver-email "jane@example.com"

ui:
	streamlit run policygate/streamlit_app.py
