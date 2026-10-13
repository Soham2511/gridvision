# Model artifact slots

Add one trusted, reviewed pipeline artifact per model under its named
subdirectory. Do not create an empty `.pkl`: pickle files can execute code when
loaded and must be inspected in a controlled environment first. Metadata and
metrics templates are present in each model folder.
