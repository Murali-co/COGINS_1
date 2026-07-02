import React, { useState, useEffect } from 'react';
import { useQuery, useMutation } from '@tanstack/react-query';
import client from '../api/client';

const ModelSelector = () => {
  const [selectedModel, setSelectedModel] = useState('');
  const [showRecommended, setShowRecommended] = useState(false);

  // Fetch available models
  const { data: modelsData, isLoading: loadingModels } = useQuery({
    queryKey: ['availableModels'],
    queryFn: async () => {
      const response = await client.get('/llm/available-models');
      return response.data;
    },
  });

  // Fetch recommended models
  const { data: recommendedData } = useQuery({
    queryKey: ['recommendedModels'],
    queryFn: async () => {
      const response = await client.get('/llm/recommended-models');
      return response.data;
    },
  });

  // Fetch user's current model preference
  const { data: userPreference } = useQuery({
    queryKey: ['userModelPreference'],
    queryFn: async () => {
      const response = await client.get('/llm/user-model-preference');
      return response.data;
    },
    onSuccess: (data) => {
      setSelectedModel(data.preferred_model);
    },
  });

  // Set model preference mutation
  const setModelMutation = useMutation({
    mutationFn: async (modelName) => {
      const response = await client.post('/llm/user-model-preference', {
        model_name: modelName,
      });
      return response.data;
    },
    onSuccess: (data) => {
      console.log('Model changed:', data);
    },
  });

  const handleModelChange = (modelName) => {
    setSelectedModel(modelName);
    setModelMutation.mutate(modelName);
  };

  if (loadingModels) {
    return <div className="p-4 text-gray-500">Loading available models...</div>;
  }

  const availableModels = modelsData?.models || [];
  const recommendedModels = recommendedData?.categories || {};

  return (
    <div className="bg-white rounded-lg shadow p-6">
      <h2 className="text-2xl font-bold mb-4">AI Model Selection</h2>
      
      <div className="mb-6">
        <h3 className="text-lg font-semibold mb-3">Current Model</h3>
        <div className="bg-blue-50 p-4 rounded-lg border border-blue-200">
          <div className="text-2xl font-bold text-blue-700">{selectedModel}</div>
          <p className="text-sm text-blue-600 mt-1">
            This model is used for all AI features (cover letters, resume tailoring, interviews, etc.)
          </p>
        </div>
      </div>

      <div className="mb-6">
        <h3 className="text-lg font-semibold mb-3">Available Models</h3>
        <div className="space-y-2 max-h-64 overflow-y-auto">
          {availableModels.length > 0 ? (
            availableModels.map((model) => (
              <button
                key={model.name}
                onClick={() => handleModelChange(model.name)}
                className={`w-full text-left p-3 rounded-lg transition ${
                  selectedModel === model.name
                    ? 'bg-green-100 border-2 border-green-500'
                    : 'bg-gray-50 border border-gray-300 hover:bg-gray-100'
                }`}
              >
                <div className="font-semibold text-gray-800">{model.name}</div>
                <div className="text-sm text-gray-600">
                  {model.size ? `${(model.size / 1e9).toFixed(1)}GB` : 'Unknown size'}
                </div>
              </button>
            ))
          ) : (
            <p className="text-gray-500">No models available. Run: ollama pull qwen2.5:7b</p>
          )}
        </div>
      </div>

      <div className="mb-6">
        <button
          onClick={() => setShowRecommended(!showRecommended)}
          className="text-blue-600 hover:text-blue-800 font-semibold"
        >
          {showRecommended ? '✓' : '+'} Recommended Models
        </button>
        
        {showRecommended && (
          <div className="mt-4 space-y-4">
            {Object.entries(recommendedModels).map(([category, models]) => (
              <div key={category} className="border-l-4 border-yellow-400 pl-4">
                <h4 className="font-semibold text-gray-800 capitalize mb-2">{category}</h4>
                <div className="space-y-2">
                  {models.map((model) => (
                    <div
                      key={model.name}
                      className="bg-yellow-50 p-3 rounded-lg border border-yellow-200"
                    >
                      <div className="flex justify-between items-start">
                        <div>
                          <div className="font-semibold text-gray-800">{model.name}</div>
                          <p className="text-sm text-gray-600">{model.description}</p>
                          <div className="flex gap-2 mt-1 text-xs">
                            <span className="bg-blue-100 text-blue-800 px-2 py-1 rounded">
                              Speed: {model.speed}
                            </span>
                            <span className="bg-purple-100 text-purple-800 px-2 py-1 rounded">
                              Quality: {model.quality}
                            </span>
                          </div>
                        </div>
                        <button
                          onClick={() => handleModelChange(model.name)}
                          className="bg-yellow-500 hover:bg-yellow-600 text-white px-3 py-1 rounded text-sm"
                        >
                          Select
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="bg-gray-50 p-4 rounded-lg border border-gray-200">
        <h3 className="font-semibold text-gray-800 mb-2">📦 Pull a New Model</h3>
        <p className="text-sm text-gray-600 mb-3">
          To use additional models, pull them from Ollama:
        </p>
        <div className="bg-gray-800 text-gray-100 p-3 rounded font-mono text-xs">
          ollama pull mistral:7b
        </div>
        <p className="text-xs text-gray-500 mt-2">
          Make sure Ollama is running: <code className="bg-gray-200 px-1">ollama serve</code>
        </p>
      </div>
    </div>
  );
};

export default ModelSelector;
