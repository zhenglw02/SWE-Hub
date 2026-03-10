def process_data(file_path, threshold):
    """
    A sample function containing various structures to test removal modifiers.
    """
    # Assignment to be removed
    data_points = []
    
    # Wrapper to be removed
    try:
        with open(file_path, 'r') as f:
            lines = f.readlines()
            # Loop to be removed
            for i, line in enumerate(lines):
                value = int(line.strip())
                # Conditional to be removed
                if value > threshold:
                    # Augmented assignment to be removed
                    value += 10
                    data_points.append(value)

    except FileNotFoundError:
        print(f"Error: File not found at {file_path}")
        return None
    
    return data_points
